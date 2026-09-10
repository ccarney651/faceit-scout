// tools/replay_bot/emit.js
// Turning a swept, segmented map into the contribution record CI already merges.
// See specs/2026-09-08-replay-bot-design.md §6.
//
// The shape here is not the bot's to choose. `owdb/contribute.py` reads
// `maps[].observations[]`, and each observation is ONE SIDE at one sample:
//
//   {side, ts, sub_map, round_no, phase, heroes: [guid...], pairs: [...]}
//
// Two conversions are easy to get wrong and are therefore done in one place:
//
//   - `ts` is MILLISECONDS. The sweep counts seconds, because that is what
//     seeking a replay deals in. Forgetting the factor would stack every
//     observation of a twenty-minute map into its first second.
//   - `heroes` are GUIDs. refs.js hands back a guid beside the display name;
//     the guid is what travels, and a name never round-trips into this file.
//
// Fields the bot cannot honestly fill are left as the absences the merge
// already tolerates - never guessed. A wrong sub_map is worse than no sub_map,
// because a null is visibly missing and a wrong one is silently believed.

(function (global) {
  'use strict';

  var SIDES = ['a', 'b'];

  // Which round a sample falls in, 1-based to match owdb's round_no. A sample
  // outside every range (which should not happen) gets null rather than a
  // fabricated round.
  function roundNoFor(sample, rounds) {
    for (var i = 0; i < rounds.length; i++) {
      if (sample.t >= rounds[i].from_t && sample.t <= rounds[i].to_t) return i + 1;
    }
    return null;
  }

  // Samples to per-side observation records, in sample order, side 'a' first.
  //
  // `attribution`, when given, is attribute.js's once-per-map result -
  // {a: {ids, conf}, b: {ids, conf}} - and applies to every observation of
  // this map alike, because a map's slot->player mapping is resolved once,
  // not per sample (specs/2026-09-10-replay-bot-player-attribution-design.md
  // §2). Absent (null, or a side with no `ids`) yields pairs: [] exactly as
  // before - a supported absence, never a guess - and `ids[i]` can itself be
  // null for a slot attribution abstained on, which is written through
  // rather than dropped: a missing player_id is a schema-tolerated absence,
  // the same as a missing pair entirely.
  function observations(samples, rounds, attribution) {
    var out = [];
    samples.forEach(function (s) {
      var round_no = roundNoFor(s, rounds);
      SIDES.forEach(function (side) {
        var heroes = (side === 'a' ? s.heroes_a : s.heroes_b).slice();
        var ids = attribution && attribution[side] && attribution[side].ids;
        out.push({
          side: side,
          ts: s.t * 1000,
          sub_map: null,
          round_no: round_no,
          phase: null,
          heroes: heroes,
          pairs: ids ? heroes.map(function (guid, i) { return [guid, ids[i] || null]; }) : [],
        });
      });
    });
    return out;
  }

  // The map's identity and the fields FACEIT owns - everything a record has
  // except its observations. Shared by mapRecord (per-sample, pre-review) and
  // mapRecordFromRounds (per-round, post-review) so the renames are stated once.
  //
  // The renames are the whole risk surface here: the feed calls a map `map` and
  // a code `code`, while the schema wants `map_name` and `demo_code`; and t1/t2
  // are side A and side B in that order. Swapping the teams would attribute
  // every comp to the opponent, and nothing downstream would notice.
  function baseRecord(code, opts) {
    return {
      match_id: code.match_id,
      game_no: code.game_no,
      demo_code: code.code,
      map_guid: code.map_guid,
      map_name: code.map,
      map_category: code.map_category,
      side_a_team_id: code.t1,
      side_a_team: code.team_a,
      side_b_team_id: code.t2,
      side_b_team: code.team_b,
      // FACEIT owns both of these. The bot watches a replay; it does not
      // adjudicate the match, and a captured ban row is not its job either.
      winner_side: null,
      bans: [],
      captured_at: (opts && opts.capturedAt) || new Date().toISOString(),
      profile: opts && opts.profile,
    };
  }

  // One captured map, ready to sit in a contribution's `maps[]` - the per-sample
  // shape, one observation per side per sample, used by run.js before review.
  function mapRecord(code, samples, rounds, opts) {
    return Object.assign(baseRecord(code, opts), {
      observations: observations(samples, rounds, opts && opts.attribution),
    });
  }

  // The same record from resolve.js's per-round output, after the operator has
  // reviewed it. See specs/2026-09-10-replay-bot-autonomous-scouting-design.md §5.
  //
  // One observation per round per side - the confirmed comp - which is the shape
  // a human contributor produces and the frequency owdb's opening-comp and
  // hero-pool derivations assume. A slot the operator left unresolved (null
  // guid) drops out of that round's comp rather than shipping a hole; a slot
  // still marked `contested` after review ships a SECOND observation for that
  // round with the runner-up swapped in, at the round's midpoint, so a real
  // mid-round hero swap is not flattened to one hero.
  function fromRounds(rounds) {
    var out = [];
    (rounds || []).forEach(function (round) {
      SIDES.forEach(function (side) {
        var slots = round[side] || [];

        var heroes = [];
        var pairs = [];
        var hasContest = false;
        slots.forEach(function (s) {
          if (!s || !s.guid) return;
          heroes.push(s.guid);
          pairs.push([s.guid, (s.player_id === undefined || s.player_id === null) ? null : s.player_id]);
          if (s.contested && s.alt_guid) hasContest = true;
        });
        if (!heroes.length) return;   // an unsampled/empty round-side ships nothing

        out.push({
          side: side, ts: Math.round(round.from_t * 1000), sub_map: null,
          round_no: round.round_no, phase: null, heroes: heroes, pairs: pairs,
        });

        if (hasContest) {
          var altHeroes = [];
          var altPairs = [];
          slots.forEach(function (s) {
            if (!s || !s.guid) return;
            var g = (s.contested && s.alt_guid) ? s.alt_guid : s.guid;
            altHeroes.push(g);
            altPairs.push([g, (s.player_id === undefined || s.player_id === null) ? null : s.player_id]);
          });
          out.push({
            side: side,
            ts: Math.round((round.from_t + (round.to_t - round.from_t) / 2) * 1000),
            sub_map: null, round_no: round.round_no, phase: null,
            heroes: altHeroes, pairs: altPairs,
          });
        }
      });
    });
    return out;
  }

  function mapRecordFromRounds(code, rounds, opts) {
    return Object.assign(baseRecord(code, opts), { observations: fromRounds(rounds) });
  }

  // What distinguishes a bot run from an operator's, and the reason the output
  // is segregated at all: merge can weight it, audit it, or drop it wholesale,
  // and bot rows can be diffed against a human's on the same map. Claiming
  // browser-0.2 here would make the bot's own output unauditable.
  var TOOL_VERSION = 'replay-bot-0.1';

  // A whole contribution file, ready to sit beside a human's in
  // data/captures/<season>/.
  function file(maps, opts) {
    return {
      format: 1,
      contributor: opts.contributor,
      tool_version: TOOL_VERSION,
      heroes: {},
      maps: maps,
    };
  }

  var Mod = {
    TOOL_VERSION: TOOL_VERSION,
    roundNoFor: roundNoFor,
    observations: observations,
    mapRecord: mapRecord,
    fromRounds: fromRounds,
    mapRecordFromRounds: mapRecordFromRounds,
    file: file,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayEmit = Mod;
})(typeof self !== 'undefined' ? self : this);
