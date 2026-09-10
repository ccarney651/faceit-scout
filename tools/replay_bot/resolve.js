// tools/replay_bot/resolve.js
// A map's per-sample reads, aggregated to a per-round per-slot result with an
// explicit confidence and the reasons an operator should look.
// See specs/2026-09-10-replay-bot-autonomous-scouting-design.md §2.
//
// The sweep samples each slot several times a round. `vote.js` already resolves
// one slot across frames and says how much the frames agreed; this groups a
// map's samples into rounds first, votes each slot inside each round, and then
// turns "the frames disagreed" / "the best frame still scored badly" / "nobody
// was placed in this slot's player" into a flag - a reason to look, never a
// verdict. A flagged slot still carries its best guess. Nothing is dropped here;
// the operator decides in the review page.
//
// PURE. run.js calls this after a map is captured; it imports vote.js and reads
// the feed's hero_roles, and touches nothing else.

(function (global) {
  'use strict';

  var Vote = require('./vote.js');

  var SIDES = ['a', 'b'];

  // Below this share of a round's frames agreeing, the winning hero is worth a
  // second look even though it won. 0.67 = "two of every three frames"; a
  // genuine read on a stable slot sits at or very near 1.0, and the live runs
  // that motivated this had their good slots unanimous.
  var SUPPORT_MIN = 0.67;

  // capture.js's own LOW_SCORE, restated rather than imported - requiring
  // capture.js would pull @napi-rs/canvas and the whole grab stack into a pure
  // module. Below this a match is a suggestion, not a reading (crop.js measured
  // correct reads on the red plate as low as 0.805, so this does not reject a
  // slot, only flags it).
  var LOW_SCORE = 0.6;

  // A round that landed fewer than this share of its planned samples was mostly
  // missed - the seeks were swallowed, or the round was shorter than the sweep
  // expected - and its comp is thin evidence.
  var SPARSE_RATIO = 0.5;

  // The samples whose time falls inside a round's [from_t, to_t].
  function samplesIn(samples, round) {
    return samples.filter(function (s) {
      return s.t >= round.from_t && s.t <= round.to_t;
    });
  }

  // The guid held second-most-often across a slot's frames, for a contested
  // slot's runner-up. Deterministic: ties break alphabetically, the same way
  // vote.js breaks them, so two runs over one replay never disagree.
  function runnerUp(guids, winner) {
    var counts = {};
    guids.forEach(function (g) {
      if (g === null || g === undefined || g === '' || g === winner) return;
      counts[g] = (counts[g] || 0) + 1;
    });
    var best = null;
    var bestN = -1;
    Object.keys(counts).sort().forEach(function (g) {
      if (counts[g] > bestN) { bestN = counts[g]; best = g; }
    });
    return best;
  }

  // One slot, resolved across a round's frames.
  //
  // `cells` is the slot's per-sample reads for this round, in sample order -
  // each a {name, guid, score}. `roleKnown` says whether the feed has a role
  // for the winning hero. `player` is {id, conf} from attribution, or null.
  function resolveSlot(cells, roleKnown, player) {
    var guids = cells.map(function (c) { return (c && c.guid) || null; });
    var v = Vote.slot(guids);
    var winner = v.name;                       // guids were passed, so name IS the guid
    var scores = cells.map(function (c) { return (c && typeof c.score === 'number') ? c.score : null; });
    var winnerScores = cells
      .filter(function (c) { return c && c.guid === winner; })
      .map(function (c) { return c.score; });
    var name = null;
    cells.forEach(function (c) { if (c && c.guid === winner && c.name) name = c.name; });

    var flags = [];
    if (winner === null) {
      flags.push('no-read');
    } else {
      if (v.contested) flags.push('contested');
      else if (v.support < SUPPORT_MIN) flags.push('low-support');
      if (winnerScores.length && Math.max.apply(null, winnerScores) < LOW_SCORE) flags.push('low-score');
      if (String(winner).indexOf('custom:') === 0 || !roleKnown(winner)) flags.push('unknown-hero');
    }
    if (player && player.id === null) flags.push('attribution-abstained');

    return {
      guid: winner,
      name: name,
      support: v.support,
      reads: scores,
      contested: v.contested,
      alt_guid: v.contested ? runnerUp(guids, winner) : null,
      player_id: player ? player.id : null,
      player_conf: player ? player.conf : null,
      flags: flags,
    };
  }

  // An empty slot, for a round no frame reached.
  function emptySlot(player) {
    return {
      guid: null, name: null, support: 0, reads: [], contested: false,
      alt_guid: null,
      player_id: player ? player.id : null,
      player_conf: player ? player.conf : null,
      flags: [],
    };
  }

  // A map's rounds, each with its resolved comp and the flags on it.
  //
  //   samples  [{ t, a: [{name,guid,score} x5], b: [...] }]  from captureMap
  //   rounds   [{ from_t, to_t }]                             from capture.roundsOf
  //   opts.heroRoles   { guid: role }  the feed's hero_roles (for unknown-hero)
  //   opts.attribution { a: {ids, conf}, b: {...} } | null    once per map
  //   opts.planned     { round_no: count }                    planned samples, for sparse-round
  function rounds(samples, rounds_, opts) {
    var o = opts || {};
    var heroRoles = o.heroRoles || {};
    var attribution = o.attribution || null;
    var planned = o.planned || {};
    var roleKnown = function (guid) { return Object.prototype.hasOwnProperty.call(heroRoles, guid); };

    return (rounds_ || []).map(function (round, i) {
      var round_no = i + 1;
      var mine = samplesIn(samples || [], round);

      var out = { round_no: round_no, from_t: round.from_t, to_t: round.to_t, a: [], b: [], flags: [] };

      SIDES.forEach(function (side) {
        var attr = attribution && attribution[side];
        for (var slot = 0; slot < 5; slot++) {
          var player = attr
            ? { id: attr.ids ? (attr.ids[slot] === undefined ? null : attr.ids[slot]) : null,
                conf: attr.conf ? (attr.conf[slot] === undefined ? null : attr.conf[slot]) : null }
            : null;
          if (!mine.length) {
            out[side].push(emptySlot(player));
            continue;
          }
          var cells = mine.map(function (s) { return s[side] && s[side][slot]; });
          out[side].push(resolveSlot(cells, roleKnown, player));
        }
      });

      if (!mine.length) {
        out.flags.push('round-unsampled');
      } else if (planned[round_no] && mine.length < planned[round_no] * SPARSE_RATIO) {
        out.flags.push('sparse-round');
      }

      return out;
    });
  }

  var Mod = {
    SUPPORT_MIN: SUPPORT_MIN,
    LOW_SCORE: LOW_SCORE,
    SPARSE_RATIO: SPARSE_RATIO,
    samplesIn: samplesIn,
    runnerUp: runnerUp,
    rounds: rounds,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayResolve = Mod;
})(typeof self !== 'undefined' ? self : this);
