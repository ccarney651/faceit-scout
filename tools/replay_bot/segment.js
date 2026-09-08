// tools/replay_bot/segment.js
// Turning a uniform sweep's observations into rounds and comps.
// See specs/2026-09-08-replay-bot-design.md §4.
//
// The sweep does not know where rounds begin. It samples on a fixed interval
// because the replay timeline exposes no round markers to seek against, so
// boundaries are RECOVERED here from the score and clock the HUD was already
// showing. Nothing upstream has to be clever about time.
//
// The distinction this module exists to hold: OPENING COMP and HERO POOL are
// not the same thing and must never be conflated.
//
//   - `opening` is the five heroes standing at the round's first sample. It is
//     a comp in owdb/comps.py's sense, and the ONLY thing safe to pass to
//     canonical_comp().
//   - `pool` is every hero seen during the round. It is scouting colour, and
//     may hold seven or eight names after swaps.
//
// Feeding a pool to canonical_comp() would mint a seven-hero "comp" with
// nonsense role counts, hashing to a comp_id no real composition shares. The
// two are kept in separate fields so that mistake has to be deliberate.

(function (global) {
  'use strict';

  // The five heroes each side opened the round with.
  function opening(samples) {
    return {
      a: samples[0].heroes_a.slice(),
      b: samples[0].heroes_b.slice(),
    };
  }

  // Every hero either side fielded during the round, swaps included. Sorted so
  // two runs over the same replay compare equal.
  function pool(samples) {
    var seen = { a: new Set(), b: new Set() };
    samples.forEach(function (s) {
      s.heroes_a.forEach(function (h) { seen.a.add(h); });
      s.heroes_b.forEach(function (h) { seen.b.add(h); });
    });
    return { a: Array.from(seen.a).sort(), b: Array.from(seen.b).sort() };
  }

  function round(samples, index) {
    return {
      index: index,
      from_t: samples[0].t,
      to_t: samples[samples.length - 1].t,
      opening: opening(samples),
      pool: pool(samples),
      samples: samples.length,
    };
  }

  // Whether the scoreline moved between two consecutive samples. Either side
  // scoring ends a round, so this is an OR - treating it as "team a scored"
  // would merge every round the opponent won into the previous one.
  function scored(prev, cur) {
    return cur.score_a !== prev.score_a || cur.score_b !== prev.score_b;
  }

  // Observations to rounds. Boundaries fall where the score moved: the sample
  // that shows the new scoreline is the first sample of the next round.
  function rounds(observations) {
    if (!observations.length) return [];
    var out = [];
    var current = [observations[0]];
    for (var i = 1; i < observations.length; i++) {
      if (scored(observations[i - 1], observations[i])) {
        out.push(round(current, out.length));
        current = [];
      }
      current.push(observations[i]);
    }
    out.push(round(current, out.length));
    return out;
  }

  var Mod = {
    opening: opening,
    pool: pool,
    rounds: rounds,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplaySegment = Mod;
})(typeof self !== 'undefined' ? self : this);
