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
    eventsViewer: 'K',
  };

  // Make sure the replay events viewer is showing.
  //
  // THE SCRUBBER ONLY DRAWS ROUND BREAKS WHILE THAT PANEL IS OPEN. Closed, a
  // three-round Control map reads as one continuous segment - confidently, and
  // wrongly, which is how the first live run produced a wrong timeline.
  //
  // TWO KEYS, IN ORDER: N then K. The media controls have to be up before the
  // events viewer will open, and N is pressed EVERY TIME because that is what
  // the client needs - measured on the rig, where a run that pressed only K sat
  // at 0.023 before and after, having done nothing at all.
  //
  // N is a toggle, so pressing it blind can hide the controls instead of
  // showing them. `mediaVisible()` catches that - the playhead is drawn only
  // while the controls are up - and one more press puts them back.
  //
  // THE VERDICT IS THE CHANGE, NOT THE LEVEL. The panel is translucent and its
  // contents vary, so how bright it reads depends on the map behind it and on
  // how much happened in the game:
  //
  //     Busan, Control      0.211 closed -> 0.755 open
  //     Gibraltar, Escort   0.024 closed -> 0.504 open
  //     Havana, Quick Play  0.000 closed -> 0.252 open
  //
  // Havana's OPEN panel reads dimmer than Busan's CLOSED one, so no absolute
  // threshold can separate them - and a threshold was what refused two maps
  // that had opened perfectly well. Every press that worked raised the fraction
  // by at least 0.25; `rise` is that, halved for margin.
  async function ensureEventsViewer(ctx) {
    var steps = [];
    var before = await ctx.read();
    if (ctx.isOpen(before)) {
      return { open: true, pressed: false, before: before, after: before, steps: steps };
    }

    if (ctx.showMedia) {
      await ctx.showMedia();
      steps.push('N');
      if (ctx.mediaVisible) {
        var up = await ctx.mediaVisible();
        if (!up) {
          // N is a toggle and it went the wrong way. Put it back.
          await ctx.showMedia();
          steps.push('N again');
          up = await ctx.mediaVisible();
        }
        if (!up) {
          return {
            open: false,
            pressed: false,
            before: before,
            after: before,
            steps: steps,
            reason: 'media controls would not show, so K has nothing to open',
          };
        }
      }
    }

    await ctx.toggle();
    steps.push('K');
    var after = await ctx.read();
    var rise = ctx.rise === undefined ? 0.125 : ctx.rise;
    return {
      open: ctx.isOpen(after) || (after - before) >= rise,
      pressed: true,
      before: before,
      after: after,
      rose: after - before,
      steps: steps,
    };
  }

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
    // Read from ctx on every use rather than captured once: the step's length
    // is measured after the driver exists, because measuring it needs the
    // driver to press the keys.
    var stepOf = function () { return ctx.stepS || 20; };
    var pos = null;      // unknown until the first seek establishes it
    var focused = false;

    // Keys go in ONE call per seek, not one per key. Each call is a process
    // spawn costing the better part of a second, so a 50-press seek sent
    // key-by-key would spend 40 seconds doing nothing but starting processes.
    async function press(keys) {
      if (!keys.length) return;
      if (!focused) {
        await ctx.focus();
        focused = true;
      }
      await ctx.sendKeys(keys);
    }

    // Seeking is counted, and now also CHECKED.
    //
    // Presses only land when the client is not already seeking - measured at
    // 700ms apart, 5 of 5; at 45ms, 1 of 5 - and a swallowed press is silent.
    // Nothing in the output looks wrong: the bot reports the position it asked
    // for, and every later sample on the map is displaced by the same amount.
    //
    // So when `ctx.position()` is supplied (it reads the playhead off the bar
    // and answers in seconds), the result is measured and corrected. THE
    // MEASUREMENT WINS: if correction runs out of attempts, `pos` becomes where
    // the replay actually is, never where it was supposed to be. A caller that
    // knows the sample is misplaced can drop it; one that was lied to cannot.
    async function seekTo(t) {
      var stepS = stepOf();
      await press(seekPlan(pos, t, stepS));
      pos = t;
      await ctx.settle();
      if (!ctx.position) return pos;

      var left = ctx.maxCorrections === undefined ? 3 : ctx.maxCorrections;
      var at = await ctx.position();
      while (at !== null && Math.abs(at - t) >= stepS / 2 && left > 0) {
        left--;
        await press(seekPlan(at, t, stepS));
        await ctx.settle();
        at = await ctx.position();
      }
      pos = (at === null) ? t : at;
      return pos;
    }

    return {
      KEY: KEY,
      position: function () { return pos; },
      // Forget where we are - after opening a different replay, where any
      // remembered position would be a lie about the new one.
      reset: function () { pos = null; focused = false; },
      seekTo: seekTo,
      pause: function () { return press([KEY.pause]); },
      // Showing the media controls moves the UI, so it settles like a seek -
      // reading the panel before it has drawn gets the state it was in before.
      mediaControls: async function () {
        await press([KEY.mediaControls]);
        await ctx.settle();
      },
      // Toggling the events panel moves the UI, so it settles like a seek.
      eventsViewer: async function () {
        await press([KEY.eventsViewer]);
        await ctx.settle();
      },
    };
  }

  var Mod = {
    KEY: KEY,
    seekPlan: seekPlan,
    ensureEventsViewer: ensureEventsViewer,
    make: make,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayDriver = Mod;
})(typeof self !== 'undefined' ? self : this);
