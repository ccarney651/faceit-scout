// tools/replay_bot/fakeio.js
// The capture, run against recorded frames instead of a live client.
//
// TWELVE REPLAY CODES WERE SPENT ON BUGS IN ONE NIGHT AND THREE OF THEM WERE
// THE SAME SHAPE: the client was not where a chunk assumed, so the chunk
// clicked blind. Every one was invisible in the output and obvious in the
// retained frames afterwards. A code imports exactly once, ever, so the frames
// are the only corpus there will be - and until now nothing could re-run the
// code against them.
//
// capture.js already takes everything that touches the machine as one injected
// object. This is that object, backed by a script instead of a rig: no
// PowerShell, no grabs, no waiting. `loadImage` is the real decoder, so the
// pixels the detectors see here are the pixels they saw on the night.
//
// What it records is as important as what it serves. A run leaves a transcript
// of every grab, key and wait, which is how a test says "the bot pressed N
// before K" rather than "the bot got the right answer" - the ordering bugs
// were never visible in the answers.

(function (global) {
  'use strict';

  var path = require('path');
  var canvas = require('@napi-rs/canvas');

  // `screen` says what is on screen at each grab, and takes whichever of three
  // forms fits the test:
  //
  //   'x.png'            the screen never changes
  //   ['a.png','b.png']  one frame per grab, in order
  //   function (ctx)     answered from what has happened so far
  //
  // The function form gets { tag, n, keys } - the tag the caller asked for, how
  // many grabs have gone before, and every key sent up to now. That is enough
  // to model a client that responds: a panel that opens once K has been
  // pressed, a replay that pauses on SPACE.
  function make(opts) {
    var o = opts || {};
    var dir = o.framesDir || null;
    var script = o.screen;
    var grabs = [];
    var keys = [];
    var kept = [];
    var logs = [];
    var last = null;
    var slept = 0;

    // A screen is usually a path to a recorded frame. It can also be a picture
    // outright - `loadImage` hands those straight back - which is how a guard
    // like "the frame is the wrong resolution" gets a test without a 7MB PNG
    // in a corpus that is not even in git.
    function resolve(name) {
      return (dir && typeof name === 'string') ? path.join(dir, name) : name;
    }

    async function grabTo(tag) {
      var ctx = { tag: tag, n: grabs.length, keys: keys.slice() };
      var name;
      if (typeof script === 'function') name = script(ctx);
      else if (Array.isArray(script)) {
        if (grabs.length >= script.length) {
          throw new Error('grab ' + (grabs.length + 1) + ' (' + tag + ') has no ' +
            'screen: the script has ' + script.length + ' - the capture went ' +
            'further than the run this was written from');
        }
        name = script[grabs.length];
      } else name = script;
      if (!name) {
        throw new Error('grab ' + (grabs.length + 1) + ' (' + tag + ') has no screen');
      }
      var p = resolve(name);
      grabs.push({ tag: tag, frame: p });
      last = p;
      return p;
    }

    async function settleAs(tag) {
      return { settled: true, frame: await grabTo(tag) };
    }

    var events = [];

    var io = {
      grabs: grabs,
      keys: keys,
      kept: kept,
      logs: logs,
      // Every computed mouse gesture the run played - a drag seek is one of
      // these - so a test can say "the sample loop dragged rather than pressed".
      events: events,
      get slept() { return slept; },

      log: function (line) { logs.push(line); },
      grabTo: grabTo,
      loadImage: function (p) {
        return typeof p === 'string' ? canvas.loadImage(p) : Promise.resolve(p);
      },
      sendKeys: async function (ks) { Array.prototype.push.apply(keys, ks); },
      playEvents: async function (evs) { Array.prototype.push.apply(events, evs); },
      settle: function () { return settleAs('settle'); },
      quiesce: function () { return settleAs('q'); },
      lastFrame: function () { return last; },
      keepAs: function (tag, src) {
        var from = src || last;
        if (!from) return null;
        kept.push({ tag: tag, frame: from });
        return from;
      },
      // Time is a thing that touches the machine too. Counted so a wait that
      // grows is visible, never actually served.
      //
      // Anything that measures a rate against the WALL CLOCK still sees real
      // time, so it reads a wait of nothing as infinite speed -
      // capture.measureRate is the one that does. Script around it rather than
      // through it.
      sleep: async function (ms) { slept += ms || 0; },
    };
    return io;
  }

  var Mod = { make: make };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayFakeIo = Mod;
})(typeof self !== 'undefined' ? self : this);
