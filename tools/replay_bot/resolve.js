// tools/replay_bot/resolve.js
// A map's per-sample reads, aggregated to a per-round per-slot result with an
// explicit confidence and the reasons an operator should look.
// See specs/2026-09-10-replay-bot-autonomous-scouting-design.md §2.
//
// The sweep samples each slot several times a round. `vote.js` resolves one
// slot across frames and says how much the frames agreed - used here only to
// catch noisy disagreement within an otherwise-stable read. The hero actually
// PRESENTED for a round is picked by `segmentWinner`, by playtime across the
// slot's confirmed segments: a fixed sampling grid makes raw sample count a
// poor stand-in for playtime whenever samples land unevenly around a swap
// (2026-09-15 - a 2-2 sample tie turned out to be an 80/20 time split in
// review). This groups a map's samples into rounds, resolves each slot inside
// each round by segment duration, and turns "no hero held a time majority" /
// "the frames disagreed" / "the best frame still scored badly" / "nobody was
// placed in this slot's player" into a flag - a reason to look, never a
// verdict. A flagged slot still carries its best guess. Nothing is dropped
// here; the operator decides in the review page.
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

  // phases.js's own ABSENT_GUID, restated rather than imported - requiring
  // phases.js would pull @napi-rs/canvas and the whole grab stack into a pure
  // module, same reason LOW_SCORE below is restated rather than imported. A
  // cell readHud found untinted (a leaver's card, gone from the HUD outright)
  // arrives here as this guid, never having reached a matcher at all.
  var ABSENT_GUID = 'ABSENT';

  // phases.js's own DEAD_GUID, restated for the same reason ABSENT_GUID is.
  // A dead-but-present player's hero does not actually change - the read is
  // not evidence of anything, for or against, so resolveSlot treats a
  // DEAD_GUID cell as if that sample never happened for this slot (2026-09-17,
  // confirmed against real captures where an undropped DEAD read corrupted a
  // slot exactly the way an undropped takeover-frame read did: skewing the
  // raw vote, or - worse - if it was the only read remaining, being reported
  // outright as ABSENT/no-read for a player who was there the whole round).
  var DEAD_GUID = 'DEAD';

  // The sentinel guid refs.json's "no hero chosen yet" reference is stored
  // under - a real ref, matched like any hero, for the grey silhouette OW
  // shows before a player locks in. Distinct from ABSENT_GUID: the card is
  // there, plainly, just without a hero yet.
  var UNSELECTED_GUID = 'UNSELECTED';

  // Seconds into a round segmentSlot ignores before segmenting - the same
  // pre-render/spawn window timeline.js's ASSEMBLE_STARTS_BY_S already
  // excludes at the map level (ASSEMBLE_STARTS_BY_S = 10 there), applied here
  // per round. A round's first segment therefore never starts before this;
  // that stretch goes uncredited to any hero rather than guessed.
  var ASSEMBLE_GRACE_S = 10;

  // A post-round/VS-takeover screen blanks the WHOLE board at once, which a
  // real disconnect never does (at most one, rarely two, players leave a
  // match). A sample where at least this many of its 10 slots read
  // ABSENT_GUID is treated as a takeover screen the fixed sampling grid
  // landed on, not ten simultaneous leavers - 2026-09-17, two real examples
  // found in review (Sheffield Larp Central vs Chud Maximus, Qwiz Esports vs
  // VQ Ragnarok) where this corrupted the round's raw vote / segment reads.
  // 6 of 10 is comfortably above any plausible simultaneous-disconnect count
  // and comfortably below "the board plainly isn't there".
  var BLANK_FRAME_ABSENT_MIN = 6;

  // The samples whose time falls inside a round's [from_t, to_t].
  function samplesIn(samples, round) {
    return samples.filter(function (s) {
      return s.t >= round.from_t && s.t <= round.to_t;
    });
  }

  // Whether a sample is a takeover screen rather than real gameplay - see
  // BLANK_FRAME_ABSENT_MIN above.
  function isBlankFrame(sample) {
    var count = 0;
    SIDES.forEach(function (side) {
      (sample[side] || []).forEach(function (c) {
        if (c && c.guid === ABSENT_GUID) count++;
      });
    });
    return count >= BLANK_FRAME_ABSENT_MIN;
  }

  // The guid held second-most-often across a slot's raw frame votes. Only
  // reached for a single-segment slot the raw vote still calls contested (a
  // fast multi-hop swap with no repeated guid to time) - a multi-segment slot
  // gets its runner-up from segmentWinner, by playtime, instead. Deterministic:
  // ties break alphabetically, the same way vote.js breaks them, so two runs
  // over one replay never disagree.
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

  // Run-length encode one slot's raw guid sequence into stable stretches, so
  // a real mid-round hero swap can be timed and reported separately from a
  // slot that never changed. `cells` and `times` are parallel arrays (the
  // slot's per-sample reads and their sample times); a read with no guid is
  // dropped rather than treated as evidence either way, and so is any read
  // inside the round's first ASSEMBLE_GRACE_S seconds.
  //
  // A new guid only becomes its own segment on a SECOND consecutive read of
  // it - a swap needs to be seen twice (on the 30s grid, roughly a minute) to
  // be counted. A single differing read is absorbed back into the run it
  // interrupted (its score still lands in that segment's `reads` array, and
  // the raw vote still sees the differing guid - so nothing is lost, it just
  // is not a swap). This was the operator's rule after the 2026-09-14 live
  // session: Goose never left Moira, yet a single misread at t620 read Brig
  // and review_out.js built a swap gallery off it.
  //
  // This re-adds the confirmation barrier that was removed on 2026-09-12, and
  // with it that decision's known cost: a fast multi-hop swap (a player seen
  // on three different heroes across three samples, one read each) never
  // repeats a guid, so its hops collapse back into the preceding segment
  // instead of one segment per hero. That is the trade the operator accepted
  // here; a genuine multi-hop is still surfaced by the raw vote as
  // `contested`/`low-support` with `alt_guid`, so it is not invisible, it
  // just has no timed segment of its own.
  //
  // Returns [{guid, name, from_t, reads}], oldest first, [] if nothing
  // survives the filtering above.
  function segmentSlot(cells, times, roundFromT) {
    var graceT = roundFromT + ASSEMBLE_GRACE_S;
    var pts = [];
    for (var i = 0; i < cells.length; i++) {
      var c = cells[i];
      var guid = c && c.guid;
      if (!guid || times[i] < graceT) continue;
      pts.push({ guid: guid, name: c.name || null, t: times[i],
        score: (typeof c.score === 'number') ? c.score : null });
    }
    if (!pts.length) return [];

    var segments = [];
    var curGuid = pts[0].guid, curName = pts[0].name, curFrom = pts[0].t, curReads = [pts[0].score];
    var pendGuid = null, pendName = null, pendT = 0, pendReads = [];

    for (var j = 1; j < pts.length; j++) {
      var p = pts[j];
      if (pendGuid !== null && p.guid === pendGuid) {
        // second consecutive read of the candidate: a real swap, confirmed
        segments.push({ guid: curGuid, name: curName, from_t: curFrom, reads: curReads });
        curGuid = pendGuid; curName = pendName; curFrom = pendT;
        curReads = pendReads.concat(p.score);
        pendGuid = null; pendReads = [];
      } else if (pendGuid !== null && p.guid === curGuid) {
        // reverted to the hero the pending read interrupted: it was noise
        curReads = curReads.concat(pendReads, p.score);
        pendGuid = null; pendReads = [];
      } else if (pendGuid !== null) {
        // a third hero while one is pending: absorb and re-pend
        curReads = curReads.concat(pendReads);
        pendGuid = p.guid; pendName = p.name; pendT = p.t; pendReads = [p.score];
      } else if (p.guid === curGuid) {
        curReads.push(p.score);
      } else {
        pendGuid = p.guid; pendName = p.name; pendT = p.t; pendReads = [p.score];
      }
    }

    if (pendGuid !== null) curReads = curReads.concat(pendReads);
    segments.push({ guid: curGuid, name: curName, from_t: curFrom, reads: curReads });
    return segments;
  }

  // The round's single presented hero for a slot, chosen by PLAYTIME across
  // the slot's confirmed segments - not by raw sample count. A fixed sampling
  // grid makes vote count a proxy for playtime only when the samples land
  // evenly around a swap; when they don't (an early hero seen twice far apart,
  // a late one seen twice right before the round ends) a straight vote ties or
  // even flips while one hero plainly held the slot for most of the round. A
  // segment's duration runs to the next segment's start, or the round's end
  // for the last one; ties (equal duration) break alphabetically by guid, the
  // same convention `vote.js`/`runnerUp` use, so two runs over one replay
  // never disagree.
  //
  // `support` is now the winner's SHARE OF TRACKED TIME (from the first
  // post-grace segment to the round's end), not a frame-agreement fraction -
  // a stable single-segment slot is always support 1, by construction.
  function segmentWinner(segments, roundToT) {
    if (!segments.length) return { guid: null, name: null, support: 0, alt: null };
    var withDur = segments.map(function (seg, i) {
      var to = (i + 1 < segments.length) ? segments[i + 1].from_t : roundToT;
      return { guid: seg.guid, name: seg.name, duration: Math.max(0, to - seg.from_t) };
    });
    var total = withDur.reduce(function (s, x) { return s + x.duration; }, 0);
    var winner = null;
    withDur.forEach(function (x) {
      if (!winner || x.duration > winner.duration ||
        (x.duration === winner.duration && x.guid < winner.guid)) winner = x;
    });
    var runner = null;
    withDur.forEach(function (x) {
      if (x.guid === winner.guid) return;
      if (!runner || x.duration > runner.duration ||
        (x.duration === runner.duration && x.guid < runner.guid)) runner = x;
    });
    return {
      guid: winner.guid,
      name: winner.name,
      support: total > 0 ? winner.duration / total : 0,
      alt: runner ? runner.guid : null,
    };
  }

  // Whether any two consecutive segments in a slot's own confirmed segment
  // chain swap between two DIFFERENT roles - physically impossible under
  // FACEIT's role lock (2026-09-17, a real Ramattra (Tank) -> Zenyatta
  // (Support) misread found in review; role-locked-comp exceptions are rare
  // enough - 53/8356 team-games, all missing-role, never a real 2-tank - that
  // this is worth flagging as a probable misread either way, not resolving).
  // Silent (no verdict on WHICH segment is wrong) when either guid's role is
  // unknown to the feed - `unknown-hero` already covers that gap.
  function hasCrossRoleSwap(segments, roleOf) {
    for (var i = 1; i < segments.length; i++) {
      var prevRole = roleOf(segments[i - 1].guid);
      var curRole = roleOf(segments[i].guid);
      if (prevRole && curRole && prevRole !== curRole) return true;
    }
    return false;
  }

  // One slot, resolved across a round's frames.
  //
  // `cells` is the slot's per-sample reads for this round, in sample order -
  // each a {name, guid, score}. `roleKnown` says whether the feed has a role
  // for the winning hero. `roleOf` returns that role (or null). `player` is
  // {id, conf} from attribution, or null.
  function resolveSlot(cells, times, roundFromT, roundToT, roleKnown, roleOf, player) {
    // A dead-but-present read is not evidence of anything - the hero does
    // not actually change while a player is dead - so it is dropped here,
    // before anything downstream (the raw vote, segmentSlot) ever sees it,
    // exactly as if that sample had never been taken for this slot.
    var kept = [], keptTimes = [];
    cells.forEach(function (c, i) {
      if (c && c.guid === DEAD_GUID) return;
      kept.push(c); keptTimes.push(times[i]);
    });
    cells = kept; times = keptTimes;

    var guids = cells.map(function (c) { return (c && c.guid) || null; });
    // The raw frame vote still drives the noise-detection flags below (a
    // single-segment slot whose frames disagreed more than SUPPORT_MIN is
    // exactly what `low-support` exists to catch) - it no longer decides which
    // hero gets PRESENTED for the round; segmentWinner does that by playtime.
    var v = Vote.slot(guids);
    var scores = cells.map(function (c) { return (c && typeof c.score === 'number') ? c.score : null; });

    var segments = segmentSlot(cells, times, roundFromT);
    var picked = segmentWinner(segments, roundToT);
    var winner = picked.guid;
    var name = picked.name;
    var support = picked.support;
    // A genuine mid-round swap (segments.length > 1) is only worth flagging
    // when no hero held a clear majority of the tracked time - two segments
    // where one plainly dominates by duration is a resolved swap, not an open
    // question, even if the raw sample count happened to tie. A single-segment
    // slot has no playtime split to judge (the whole window is one hero by
    // construction), so it falls back to the raw vote - the case that still
    // needs catching is a fast multi-hop swap (each hero read once, never
    // confirmed twice) collapsing onto its first-read hero while the reads
    // themselves plainly disagreed.
    var contested = segments.length > 1 ? support <= 0.5 : v.contested;

    var winnerScores = cells
      .filter(function (c) { return c && c.guid === winner; })
      .map(function (c) { return c.score; });

    var flags = [];
    if (winner === null) {
      flags.push('no-read');
    } else if (winner === ABSENT_GUID) {
      // Confidently the truth, not a data-quality problem - see ABSENT_GUID.
      flags.push('player-absent');
    } else if (winner === UNSELECTED_GUID) {
      // Also confidently the truth - see UNSELECTED_GUID.
      flags.push('not-picked');
    } else {
      if (contested) flags.push('contested');
      else if (v.support < SUPPORT_MIN && segments.length <= 1) flags.push('low-support');
      if (winnerScores.length && Math.max.apply(null, winnerScores) < LOW_SCORE) flags.push('low-score');
      if (String(winner).indexOf('custom:') === 0 || !roleKnown(winner)) flags.push('unknown-hero');
      if (segments.length > 1 && hasCrossRoleSwap(segments, roleOf)) flags.push('cross-role-swap');
    }
    // A leaver has nobody to attribute by construction - player-absent
    // already says so, so this would only be the same fact twice.
    if (winner !== ABSENT_GUID && player && player.id === null) flags.push('attribution-abstained');

    return {
      guid: winner,
      name: name,
      support: support,
      reads: scores,
      contested: contested,
      // Multi-segment: picked.alt is the second-longest-playtime hero. Single-
      // segment (the fast-multi-hop case above): there is no second segment to
      // ask, so fall back to the raw vote's runner-up.
      alt_guid: contested ? (picked.alt || runnerUp(guids, winner)) : null,
      segments: segments,
      player_id: player ? player.id : null,
      player_conf: player ? player.conf : null,
      flags: flags,
    };
  }

  // An empty slot, for a round no frame reached.
  function emptySlot(player) {
    return {
      guid: null, name: null, support: 0, reads: [], contested: false,
      alt_guid: null, segments: [],
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
    var roleOf = function (guid) { return heroRoles[guid] || null; };

    return (rounds_ || []).map(function (round, i) {
      var round_no = i + 1;
      var mine = samplesIn(samples || [], round);
      var blankDropped = 0;
      mine = mine.filter(function (s) {
        if (isBlankFrame(s)) { blankDropped++; return false; }
        return true;
      });

      var out = { round_no: round_no, from_t: round.from_t, to_t: round.to_t, a: [], b: [], flags: [] };
      if (blankDropped) out.flags.push('takeover-frame');

      SIDES.forEach(function (side) {
        var attr = attribution && attribution[side];
        var times = mine.map(function (s) { return s.t; });
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
          out[side].push(resolveSlot(cells, times, round.from_t, round.to_t, roleKnown, roleOf, player));
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

  // Flags that are the truth, confidently read, rather than a reason to
  // doubt the read - `contested` because segmentWinner already resolved it
  // with a real confidence number, `not-picked` because UNSELECTED_GUID is
  // itself the correct answer and every map's opening seconds produces it on
  // every slot, not a matcher failure worth an operator's time.
  //
  // `player-absent` is deliberately NOT here: a leaver is rare enough (unlike
  // "still picking", which happens on every single map) that the operator
  // asked to see it - 2026-09-16.
  var BENIGN_FLAGS = { contested: true, 'not-picked': true };

  // Whether a map's rounds carry anything worth the operator's eyes. Every
  // flag not in BENIGN_FLAGS does - no-read, low-score, low-support,
  // unknown-hero, attribution-abstained, and the round-level
  // round-unsampled/sparse-round. Drives review_out.js's initial `status`, so
  // a flag-free (or benign-only) map is auto-reviewed instead of sitting in
  // the queue with nothing for a human to actually check.
  function needsReview(rounds) {
    return (rounds || []).some(function (rd) {
      if ((rd.flags || []).length) return true;
      return SIDES.some(function (side) {
        return (rd[side] || []).some(function (s) {
          return (s.flags || []).some(function (f) { return !BENIGN_FLAGS[f]; });
        });
      });
    });
  }

  var Mod = {
    SUPPORT_MIN: SUPPORT_MIN,
    needsReview: needsReview,
    LOW_SCORE: LOW_SCORE,
    SPARSE_RATIO: SPARSE_RATIO,
    ABSENT_GUID: ABSENT_GUID,
    DEAD_GUID: DEAD_GUID,
    UNSELECTED_GUID: UNSELECTED_GUID,
    BLANK_FRAME_ABSENT_MIN: BLANK_FRAME_ABSENT_MIN,
    samplesIn: samplesIn,
    runnerUp: runnerUp,
    hasCrossRoleSwap: hasCrossRoleSwap,
    isBlankFrame: isBlankFrame,
    rounds: rounds,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayResolve = Mod;
})(typeof self !== 'undefined' ? self : this);
