// tools/replay_bot/sweep.js
// Walking one replay's timeline and collecting what the HUD showed.
// See specs/2026-09-08-replay-bot-design.md §4.
//
// The sweep is deliberately dumb. It seeks on a fixed interval and keeps
// whatever read back, because the replay timeline exposes no round markers to
// seek against - segment.js recovers the structure afterwards from the score
// the HUD was already showing. Trying to be clever here would mean searching a
// timeline against an oracle that does not exist.
//
// Everything that touches the outside world is injected: `driver` seeks,
// `grab` produces a frame, `read` turns a frame into an observation or null.
// So this module is exercised end to end without a game, and the same code
// drives a directory of recorded PNGs as drives a live client.
//
// Two stopping conditions, and they are not the same:
//
//   - `maxInvalid` consecutive unreadable frames means the replay ENDED. One
//     bad frame does not - a killcam or a scoreboard overlay reads as nothing
//     and the map is still going - so the counter resets on any good read.
//   - `capS` is the backstop for a replay that never stops reading. Without it
//     a single stuck map could eat the whole patch window.

(function (global) {
  'use strict';

  // Walk the timeline, returning observations in sample order.
  async function run(opts) {
    var driver = opts.driver;
    var grab = opts.grab;
    var read = opts.read;
    var intervalS = opts.intervalS;
    var maxInvalid = opts.maxInvalid;
    var capS = opts.capS;

    var out = [];
    var invalid = 0;

    for (var t = 0; t <= capS; t += intervalS) {
      await driver.seekTo(t);
      var frame = await grab(t);
      var got = await read(frame, t);

      if (!got) {
        invalid += 1;
        if (invalid >= maxInvalid) break;
        continue;
      }

      invalid = 0;
      out.push(Object.assign({ t: t }, got));
    }

    return out;
  }

  var Mod = {
    run: run,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplaySweep = Mod;
})(typeof self !== 'undefined' ? self : this);
