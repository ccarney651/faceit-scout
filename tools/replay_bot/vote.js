// tools/replay_bot/vote.js
// Resolving one slot's hero from the many frames that saw it.
// See specs/2026-09-08-replay-bot-design.md §4.
//
// The sweep samples a slot repeatedly through a round; a human snapshotting
// once per round never gets that. This module spends the redundancy.
//
// It exists because a confidence score cannot do this job. Measured on a real
// frame, correct reads on the red plate ran as low as 0.805 - so a threshold
// strict enough to reject a bad read would throw away good ones. Agreement
// across frames separates noise from signal where a single number cannot.
//
// What it must NOT do is quietly average away a real hero swap. A slot that is
// genuinely split is reported as `contested` so the caller can treat it as two
// heroes rather than pick a winner - the difference between "this read was
// noisy" and "they swapped mid-round" is real, and only the caller knows which
// matters.

(function (global) {
  'use strict';

  // Accepts plain hero names or {name, score} readings, so callers can pass
  // whichever they already hold.
  function nameOf(r) {
    return (r && typeof r === 'object') ? r.name : r;
  }

  // The hero a slot held, by agreement across the frames that saw it.
  function slot(readings) {
    if (!readings || !readings.length) {
      return { name: null, support: 0, contested: false, total: 0 };
    }

    var counts = new Map();
    readings.forEach(function (r) {
      var n = nameOf(r);
      if (n === null || n === undefined) return;
      counts.set(n, (counts.get(n) || 0) + 1);
    });

    if (!counts.size) {
      return { name: null, support: 0, contested: false, total: readings.length };
    }

    // Most frequent wins; ties break alphabetically so two runs over the same
    // replay can never disagree because of Map insertion order.
    var best = null;
    var bestN = -1;
    Array.from(counts.keys()).sort().forEach(function (n) {
      var c = counts.get(n);
      if (c > bestN) { bestN = c; best = n; }
    });

    var support = bestN / readings.length;
    return {
      name: best,
      support: support,
      contested: support <= 0.5,
      total: readings.length,
    };
  }

  var Mod = { slot: slot };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayVote = Mod;
})(typeof self !== 'undefined' ? self : this);
