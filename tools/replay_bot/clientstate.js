// tools/replay_bot/clientstate.js
// Reading where the client is - in a replay, in the ESC menu, on the replay
// list - and the one recovery that belongs with it, clearing a stuck ESC menu.
// See ARCHITECTURE.md §14.
//
// Extracted from run.js so the console (tools/replay_bot/console/) can ask the
// same questions run.js asks between maps without pulling in the whole
// unattended loop. Every function here takes the injected `io` (capture.js's
// makeIo, or fakeio) rather than grabbing frames itself, so it runs offline
// too.
//
// WHY PICTURES WORK FOR MENUS AND NOT REPLAYS. Two frames of the ESC menu a
// beat apart differ by 3.4 and differ from a replay by 82 - but two frames of a
// REPLAY differ from each other by 55, because the game behind the HUD is a
// moving scene. So `onScreen` fingerprints the static menus; `inReplay` reads
// the HUD's own structure instead.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');
  var S = require('./screen.js');
  var calib = require('./calib.js');
  var Crop = require('./crop.js');
  var TIMING = require('./timing.js');

  var wait = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  function readJson(p, fallback) {
    try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
  }

  // Whether a replay is on screen, judged by the two team plates being tinted.
  //
  // NOT THE PLAYHEAD, which is what this used and why a run once did nothing at
  // all: the media controls are HIDDEN when a replay opens, so there is no
  // scrubber to find. The bot waited ninety seconds for one inside a replay
  // that was already playing, gave up, and then ran the import chunk from
  // inside that replay - clicking at coordinates that mean something else there.
  //
  // The plates are drawn whether the controls are up or not.
  async function inReplay(io) {
    try {
      var img = await io.loadImage(await io.grabTo('probe'));
      return calib.hudPresent(Crop.hudTint(img, calib));
    } catch (e) {
      return false;
    }
  }

  // Whether the client is sitting on a known static screen (screens/<name>.json,
  // recorded by screen.js). Menus can be recognised as pictures; replays cannot
  // - see the file header.
  async function onScreen(io, name) {
    try {
      var known = readJson(path.join(__dirname, 'screens', name + '.json'), null);
      if (!known) return false;
      var img = await io.loadImage(await io.grabTo('probe'));
      return S.looksLike(S.thumb(img), known.thumb).same;
    } catch (e) {
      return false;
    }
  }

  var escMenuUp = function (io) { return onScreen(io, 'esc-menu'); };

  // Whether the client is sitting on the career-profile REPLAYS list.
  //
  // THE IMPORT CHUNK NAVIGATES FROM WHEREVER IT IS, so starting a run already on
  // this screen puts its first clicks somewhere else entirely. That is how
  // 7V4END was lost: the code never imported, the bot waited its ninety seconds
  // for a replay that was never opening, and every code after it worked because
  // leaving the first map normalises the state. Only the FIRST code of a run is
  // exposed, which is exactly the kind of fault that hides.
  //
  // The list's contents change as replays are imported and evicted, and that
  // does not matter: across ninety seconds of probes the fingerprint moved
  // between 0.6 and 5.3 against a threshold of 18, while a replay sits at 100
  // and the ESC menu at 121.
  var replayHistoryUp = function (io) { return onScreen(io, 'replay-history'); };

  // Poll until the replay is (or is no longer) on screen. `isReady` defaults to
  // inReplay and is a seam for tests and for the console, which waits on other
  // conditions too.
  async function waitFor(io, want, timeoutMs, label, isReady) {
    var ready = isReady || inReplay;
    var nap = (io && io.sleep) || wait;
    var until = Date.now() + timeoutMs;
    while (Date.now() < until) {
      if (await ready(io) === want) return true;
      await nap(TIMING.poll.ms);
    }
    throw new Error('timed out after ' + Math.round(timeoutMs / 1000) +
      's waiting for ' + label);
  }

  // Clear the ESC menu if it is up. A leave-replay whose closing click missed
  // leaves it up, and the import chunk then clicks SOCIAL and CAREER PROFILE
  // instead of the replay list - a spent code and nothing captured.
  //
  // ESC is pressed up to `tries` times, re-checking between each, because one
  // press is not reliably taken (see TIMING.esc.tries): the client drops a key
  // that lands mid-transition. It only ever presses while the menu still reads
  // as up, so an extra press cannot land somewhere it matters. If the menu
  // outlasts every press the map is failed - but a frame is kept first, tagged
  // with the code, because the 2026-09-10 "will not close" failure left nothing
  // to diagnose from.
  //
  // Returns the number of presses it took (0 if the menu was not up). `isUp`
  // defaults to the screen-fingerprint check and is a seam for tests.
  async function clearEscMenu(io, opts) {
    var sendKeys = opts.sendKeys;
    var napMs = opts.wait;
    var escWait = opts.escWait;
    var tries = opts.tries;
    var tag = opts.tag;
    var log = opts.log || function () {};
    var isUp = opts.isUp || escMenuUp;
    var n = 0;
    while (await isUp(io)) {
      if (n >= tries) {
        var kept = null;
        try {
          var frame = await io.grabTo('esc-stuck');
          kept = await io.keepAs('esc-stuck-' + tag, frame);
        } catch (e) { /* diagnosis is best-effort; the throw below is the point */ }
        throw new Error('the ESC menu will not close after ' + tries + ' presses - the ' +
          'client is not where the chunks expect it' +
          (kept ? ' (frame kept: ' + path.basename(kept) + ')' : ''));
      }
      log(n === 0
        ? 'the ESC menu is up - clearing it before importing'
        : 'the ESC menu is still up - ESC again (' + (n + 1) + '/' + tries + ')');
      await sendKeys(['ESC']);
      await napMs(escWait);
      n++;
    }
    return n;
  }

  var Mod = {
    inReplay: inReplay,
    onScreen: onScreen,
    escMenuUp: escMenuUp,
    replayHistoryUp: replayHistoryUp,
    waitFor: waitFor,
    clearEscMenu: clearEscMenu,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayClientState = Mod;
})(typeof self !== 'undefined' ? self : this);
