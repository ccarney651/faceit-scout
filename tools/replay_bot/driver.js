// tools/replay_bot/driver.js
// Driving the replay viewer: the one module that sends keys to the game.
// See specs/2026-09-08-replay-bot-design.md §1.1 and §4.
//
// THIS IS THE ToS-RELEVANT SURFACE, deliberately confined to one file. Every
// other module reads pixels, which is ordinary use; this one automates the
// client, which the Blizzard EULA prohibits. Keeping it alone here means there
// is exactly one thing to swap if authorisation is ever obtained, and exactly
// one thing to point at recorded frames for offline work.
//
// Seeking is arithmetic, not scrubbing. JUMP TO START (B) gives a known origin
// and REPLAY FORWARD (X) moves in fixed 20s steps, so any target on that grid
// is an exact number of presses from somewhere known. Dragging the scrubber to
// a pixel would be both imprecise and mouse work; this cannot drift, because
// every position is counted rather than estimated.
//
// Measured facts that shape this file:
//
//   - Keys only land when Overwatch is FOREGROUND. PostMessage, SendMessage and
//     AttachThreadInput were all measured on the rig; none delivers to an
//     unfocused window. So focus is taken once per map and held for that map's
//     whole batch, rather than snatched for each of nine samples.
//   - After a seek the UI shifts into place for under a second. Reading during
//     that window gets a HUD mid-transition, so `settle` runs before anything
//     looks at the screen. The caller decides how to settle - comparing
//     consecutive grabs beats trusting a fixed delay.

(function (global) {
  'use strict';

  var KEY = {
    jumpToStart: 'B',
    forward: 'X',
    back: 'Z',
    pause: 'SPACE',
    mediaControls: 'N',
  };

  // The keypresses that move playback from `fromT` to `toT`.
  //
  // `fromT` of null means the position is unknown - a freshly opened replay -
  // and is never guessed at, because a wrong origin silently displaces every
  // later sample on the map.
  function seekPlan(fromT, toT, stepS) {
    var forwardFromStart = [KEY.jumpToStart];
    var steps = Math.round(toT / stepS);
    for (var i = 0; i < steps; i++) forwardFromStart.push(KEY.forward);

    if (fromT === null || fromT === undefined) return forwardFromStart;
    if (fromT === toT) return [];

    if (toT > fromT) {
      var fwd = [];
      var n = Math.round((toT - fromT) / stepS);
      for (var j = 0; j < n; j++) fwd.push(KEY.forward);
      return fwd;
    }

    // Rewinding is a choice between pressing back, or restarting and running
    // forward again. Each press is a round trip to the game, so take whichever
    // is shorter - late in a long map, restarting wins easily.
    var rew = [];
    var b = Math.round((fromT - toT) / stepS);
    for (var k = 0; k < b; k++) rew.push(KEY.back);
    return rew.length <= forwardFromStart.length ? rew : forwardFromStart;
  }

  // `ctx` supplies the three things that touch the outside world:
  //   send(key)  - deliver one keypress to the game
  //   focus()    - bring the window forward, since keys need it
  //   settle()   - wait until the UI has stopped moving after a seek
  function make(ctx) {
    var stepS = ctx.stepS || 20;
    var pos = null;      // unknown until the first seek establishes it
    var focused = false;

    async function press(key) {
      if (!focused) {
        await ctx.focus();
        focused = true;
      }
      await ctx.send(key);
    }

    async function seekTo(t) {
      var plan = seekPlan(pos, t, stepS);
      for (var i = 0; i < plan.length; i++) await press(plan[i]);
      pos = t;
      await ctx.settle();
      return pos;
    }

    return {
      KEY: KEY,
      position: function () { return pos; },
      // Forget where we are - after opening a different replay, where any
      // remembered position would be a lie about the new one.
      reset: function () { pos = null; focused = false; },
      seekTo: seekTo,
      pause: function () { return press(KEY.pause); },
      mediaControls: function () { return press(KEY.mediaControls); },
    };
  }

  var Mod = {
    KEY: KEY,
    seekPlan: seekPlan,
    make: make,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayDriver = Mod;
})(typeof self !== 'undefined' ? self : this);
