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

  // Slot STATES, not heroes: resolve.js's ABSENT_GUID/UNSELECTED_GUID/DEAD_GUID
  // (same set as reprocess_hero_match.js's SENTINELS). contribute.py writes
  // `heroes` verbatim, so any of these reaching a record is a hero called
  // "ABSENT" in a comp on the site. A list, not a "starts with 0x" rule,
  // because custom:* guids are real heroes.
  var SENTINELS = { ABSENT: true, UNSELECTED: true, DEAD: true };
  function isHero(guid) { return !!guid && !SENTINELS[guid]; }

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
        var slots = side === 'a' ? s.heroes_a : s.heroes_b;
        var ids = attribution && attribution[side] && attribution[side].ids;
        // Pair by SLOT before dropping sentinels - ids[i] belongs to slot i, so
        // filtering first would shift every later player onto the wrong hero.
        var pairs = slots.map(function (guid, i) { return [guid, ids ? (ids[i] || null) : null]; })
          .filter(function (p) { return isHero(p[0]); });
        if (!pairs.length) return;
        out.push({
          side: side,
          ts: s.t * 1000,
          sub_map: null,
          round_no: round_no,
          phase: null,
          heroes: pairs.map(function (p) { return p[0]; }),
          pairs: ids ? pairs : [],
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
      // The map's real length in seconds, measured off the replay's scrubber
      // bar by capture.js. Absent when a human capture (or an old artifact)
      // did not measure it - never estimated here: a null is honestly missing,
      // the same as the other fields the merge tolerates. The site falls back
      // to its flat per-mode estimate where this is null.
      duration_sec: (opts && opts.durationSec) || null,
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
  // reviewed it. See specs/2026-09-10-replay-bot-autonomous-scouting-design.md §5
  // and specs/2026-09-12-replay-bot-segment-observations-design.md.
  //
  // One observation per DISTINCT segment-start time across a round-side's 5
  // slots - not one per round. A round where nothing swapped has exactly one
  // segment per slot, all starting together, so it still ships exactly one
  // observation (the common case, unchanged in shape). A round with a real
  // mid-round swap ships one extra observation at the swap's own timestamp,
  // with only the slot(s) that actually swapped changing between them.
  //
  // A slot's `segments` is `Array.isArray` when resolve.js computed it
  // (segmentSlot() - real segments, or `[]` if nothing survived the
  // assemble-grace/no-read filtering). When it is `undefined`/`null` - a
  // human hero correction (review/server.js's applyCorrections) or an older
  // pre-segmentation artifact - a slot with a guid is treated as one segment
  // spanning the whole round, at the round's own from_t: a correction is an
  // assertion about the whole round, not a machine read subject to
  // pre-render noise, so it does not get the assemble-grace treatment.
  function slotSegments(s, round) {
    if (!s) return [];
    if (Array.isArray(s.segments)) return s.segments;
    if (!s.guid) return [];
    return [{ guid: s.guid, name: s.name, from_t: round.from_t, reads: [] }];
  }

  function fromRounds(rounds) {
    var out = [];
    (rounds || []).forEach(function (round) {
      SIDES.forEach(function (side) {
        var slots = round[side] || [];
        var slotSegs = slots.map(function (s) { return slotSegments(s, round); });

        var boundarySet = {};
        slotSegs.forEach(function (segs) {
          segs.forEach(function (seg) { boundarySet[seg.from_t] = true; });
        });
        var boundaries = Object.keys(boundarySet).map(Number).sort(function (a, b) { return a - b; });

        boundaries.forEach(function (t) {
          var heroes = [];
          var pairs = [];
          slotSegs.forEach(function (segs, slotIdx) {
            var active = null;
            for (var k = 0; k < segs.length; k++) {
              if (segs[k].from_t <= t) active = segs[k]; else break;
            }
            if (!active || !isHero(active.guid)) return;
            var s = slots[slotIdx];
            heroes.push(active.guid);
            pairs.push([active.guid, (s.player_id === undefined || s.player_id === null) ? null : s.player_id]);
          });
          if (!heroes.length) return;
          out.push({
            side: side, ts: Math.round(t * 1000), sub_map: null,
            round_no: round.round_no, phase: null, heroes: heroes, pairs: pairs,
          });
        });
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
    slotSegments: slotSegments,
    mapRecordFromRounds: mapRecordFromRounds,
    file: file,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayEmit = Mod;
})(typeof self !== 'undefined' ? self : this);
