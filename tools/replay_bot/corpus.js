// tools/replay_bot/corpus.js
// The frames the detectors are judged against, and what a human saw in each.
//
// A REPLAY CODE IMPORTS EXACTLY ONCE, EVER. A map the bot read badly cannot be
// captured again on this account, so the retained frames are the only corpus
// there will ever be - and they are worth nothing unless something says what is
// actually in them. Every entry below was opened and looked at. Nothing here
// was labelled by running a detector over it, because a detector graded against
// its own output grades nothing.
//
// The frames themselves are NOT in git - see frames/README.md, they are a few
// megabytes each. This file is the part worth keeping: the names, and the
// reason each one is here. Tests skip themselves when the frames are absent,
// so a checkout without them is green rather than broken.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');

  var DIR = path.join(__dirname, 'frames');

  // `open` and `hud` are what the picture shows, not what any code says.
  var WITNESSES = {
    'panel-open': {
      file: 'cap-t180-34.png',
      saw: 'A replay with the events viewer open - ROUND 1/2/3 stacked down ' +
        'the left - over an explosion bright enough to wash team A\'s tint ' +
        'down to 15.1, which is 0.1 above the threshold that decides whether ' +
        'a replay is on screen at all.',
      open: true, hud: true, playhead: true,
    },
    'panel-shut-bright': {
      file: 'cap-zero-51.png',
      saw: 'Route 66 in daylight, panel shut, media controls up and the ' +
        'playhead parked at the far left. The brightest closed panel here.',
      open: false, hud: true, playhead: true,
    },
    'panel-shut-dark': {
      file: 'cap-pause-80.png',
      saw: 'Rialto at night, panel shut. The box falls on sky and a building ' +
        'face, both smooth, so a flatness test alone calls this open.',
      open: false, hud: true, playhead: true,
    },
    'loading': {
      file: 'cap-pause-74.png',
      saw: 'The SPECTATING / KING\'S ROW loading screen. No replay, no HUD, ' +
        'no panel - and the box falls on flat sky and brick.',
      open: false, hud: false, playhead: true,
    },
    'assemble': {
      file: 'cap-timeline-71.png',
      saw: 'A replay in the assemble phase: GET READY on the clock, both team ' +
        'plates up, and no media controls at all. The frame that proves the ' +
        'playhead cannot answer "is a replay on screen".',
      open: false, hud: true, playhead: false,
    },
    'black': {
      file: 'cap-t180-36.png',
      saw: 'A black loading screen, taken as the t=180 sample. Perfectly flat ' +
        'everywhere, and both tints read 0.0.',
      open: false, hud: false, playhead: false,
    },
    'esc-menu': {
      file: 'cap-probe-84.png',
      saw: 'The ESC menu - SOCIAL / CAREER PROFILE / OPTIONS / LEAVE GAME. ' +
        'The screen a missed leave-replay click leaves up, and the one the ' +
        'next import then clicked its way through. screens/esc-menu.json was ' +
        'fingerprinted from this frame.',
      open: false, hud: false, playhead: false,
    },
    'esc-menu-again': {
      file: 'cap-probe-80.png',
      saw: 'The same ESC menu a moment later, which is how far apart two ' +
        'frames of one static screen sit.',
      open: false, hud: false, playhead: false,
    },
  };


  // The events panel, open or shut, on sixteen more frames.
  //
  // Labelled the way the rich witnesses above were and in one sitting: the
  // 500x200 panel box cropped out of each frame and tiled into one picture, so
  // "are the ROUND rows there" is answered by looking at all sixteen at once.
  // No detector was consulted. This is the population a panel test needs -
  // eight of anything is not enough to catch a detector that is right about
  // bright maps and wrong about dark ones.
  var PANELS = [
    { file: 'cap-panel-13.png', open: true },
    { file: 'cap-panel-72.png', open: true },
    { file: 'cap-panel-90.png', open: true },
    { file: 'cap-t0-35.png', open: true },
    { file: 'cap-t240-17.png', open: true },
    { file: 'cap-t420-44.png', open: true },
    { file: 'cap-pos-12.png', open: true },
    { file: 'cap-one-9.png', open: true },
    { file: 'cap-panel-10.png', open: false },
    { file: 'cap-panel-69.png', open: false },
    { file: 'cap-panel-87.png', open: false },
    { file: 'cap-t720-16.png', open: false },
    { file: 'cap-timeline-5.png', open: false },
    { file: 'cap-timeline-49.png', open: false },
    { file: 'cap-settle-38.png', open: false },
    { file: 'cap-rate-57.png', open: false },
  ];

  // Every frame with a panel verdict on it, witnesses included.
  function panels() {
    return PANELS.concat(Object.keys(WITNESSES).map(function (k) {
      return { file: WITNESSES[k].file, open: WITNESSES[k].open };
    }));
  }

  function file(name) {
    var w = WITNESSES[name];
    if (!w) throw new Error('no witness called ' + name);
    return path.join(DIR, w.file);
  }

  function at(f) { return path.join(DIR, f); }

  function missing() {
    return panels().map(function (p) { return p.file; })
      .filter(function (f, i, a) { return a.indexOf(f) === i; })
      .filter(function (f) { return !fs.existsSync(at(f)); });
  }

  // The reason a whole file's tests skip, or null when the frames are there.
  // Named so the skip says which frames to go and find.
  function absent() {
    var m = missing();
    if (!m.length) return null;
    return 'frames/ is missing ' + m.length + ' of the corpus (' +
      m.slice(0, 3).join(', ') + (m.length > 3 ? ', ...' : '') +
      ') - they are gitignored, see frames/README.md';
  }

  function named(pred) {
    return Object.keys(WITNESSES).filter(function (k) { return pred(WITNESSES[k]); });
  }

  var Mod = {
    DIR: DIR,
    WITNESSES: WITNESSES,
    PANELS: PANELS,
    panels: panels,
    file: file,
    at: at,
    missing: missing,
    absent: absent,
    named: named,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCorpus = Mod;
})(typeof self !== 'undefined' ? self : this);
