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

  // One captured map, ready to sit in a contribution's `maps[]`.
  //
  // The renames are the whole risk surface here: the feed calls a map `map` and
  // a code `code`, while the schema wants `map_name` and `demo_code`; and t1/t2
  // are side A and side B in that order. Swapping the teams would attribute
  // every comp to the opponent, and nothing downstream would notice.
  function mapRecord(code, samples, rounds, opts) {
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
      profile: opts.profile,
      observations: observations(samples, rounds, opts && opts.attribution),
    };
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
    file: file,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayEmit = Mod;
})(typeof self !== 'undefined' ? self : this);
