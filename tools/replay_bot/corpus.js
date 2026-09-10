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
//
// THEY LIVE IN frames/corpus/ BECAUSE THE BOT REUSES FILENAMES. A run names
// its frames cap-<tag>-<n>.png (or .bmp for a scratch frame - see
// frames/README.md) with n restarting at zero every time, so the next run
// silently overwrites the last one's. This corpus originally pointed
// straight at frames/, and a five-map run replaced three labelled witnesses -
// including the frame whose 15.1 tint was the entire evidence for reading the
// team plates off the portrait band. Every test still passed, because the
// replacements happened to fall on the same side of every threshold. The
// labels were describing pictures that no longer existed.
//
// frames/corpus/ is copied by hand and never written by a run. When a witness
// is added, copy it in - a name here that points at frames/ is a label with a
// countdown on it.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');

  var DIR = path.join(__dirname, 'frames', 'corpus');

  // `open` and `hud` are what the picture shows, not what any code says.
  var WITNESSES = {
    'panel-open': {
      file: 'cap-t180-34.png',
      saw: 'A replay with the events viewer open and the media controls up. ' +
        'NOT the frame originally labelled here - that one caught an explosion ' +
        'bright enough to wash team A down to a tint of 15.1, and a later run ' +
        'overwrote it before the corpus was moved somewhere safe. The reading ' +
        'it carried is recorded in crop.hudTint and in the commit that made ' +
        'it; the picture is gone.',
      open: true, hud: true, playhead: true,
    },
    'dim-replay': {
      file: 'cap-pos-42.png',
      saw: 'The dimmest frame in the corpus with both team plates actually ' +
        'drawn: a minimum tint of 27.6 against a threshold of 15. Everything ' +
        'reading lower turns out to be a seek caught mid-transition, with the ' +
        'plates not yet painted at all - which hudPresent is right to refuse. ' +
        'This is the frame that says how much room the threshold really has.',
      open: true, hud: true, playhead: true,
    },
    'mid-seek': {
      file: 'cap-q-147.png',
      saw: 'A post-seek grab with NO PLAYER PLATES AT ALL - team headers, an ' +
        'open events panel, a playhead, and darkness where the portraits go. ' +
        'Its tint of 7.3 is stray scene light, not a plate. Reading this ' +
        'frame would produce ten confident-looking heroes out of nothing, ' +
        'which is why the tint is checked before a sample is believed, and ' +
        'why there is now a wait after a seek.',
      open: true, hud: false, playhead: true,
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
    'replay-history': {
      file: 'cap-probe-5.png',
      saw: 'The career-profile REPLAYS list - IMPORTED (10), a row per replay, ' +
        'ESC/BACK bottom right. The screen the client was sitting on when ' +
        '7V4END failed to import: open-import navigates from wherever it is, ' +
        'so its first clicks landed here instead of on a menu, and the bot ' +
        'then waited ninety seconds for a replay that was never opening.',
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
  // Tonight's frames, taken live off RCR3NK on a bright one-round map. This is
  // the state neither detector had, and both were wrong about it: the events
  // panel is plainly open and read 0.170 against a threshold of 0.15, and the
  // replay is plainly on screen and read as no replay at all.
  var LIVE = [
    { file: 'probe-panelopen-live.png', open: true, hud: true,
      saw: 'RCR3NK paused, panel open, media controls up. ONE round row, where ' +
        'every other open frame here has two or three - the reading that ' +
        'depends on the round count nearly refused this map.' },
    { file: 'probe-panelshut-live.png', open: false, hud: true,
      saw: 'The same frame with K pressed once. The only open/shut pair here ' +
        'taken on one map, seconds apart, with nothing else changed.' },
    { file: 'probe-pre-3x.png', open: true, hud: true,
      saw: 'The same replay with the skip interval at 20, before the ' +
        'set-interval chunk was replayed at 3x.' },
    { file: 'probe-post-3x.png', open: true, hud: true,
      saw: 'And at 60, after. The pair that shows the chunk landed: the two ' +
        'frames differ by 0.061 over the whole picture.' },
  ];

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

  // Frames with legible player names, for nameplate.js/attribute.js testing.
  // `saw` is the ground truth transcribed by hand off the ten name plates -
  // real tesseract reads against it as a live sanity check, but the node:test
  // suite exercises the crop against an injected OCR (§7 of the design), so
  // this corpus entry does not need to be graded automatically to be useful.
  var NAMEPLATES = [
    {
      file: 'cap-t0-741.png',
      saw: 'A FACEIT league replay (E9RCSH, Neon Junction) at t=0, assemble ' +
        'phase, both team plates fully drawn. Side a: NOKI, VILPERTTIS, ' +
        'JØPEZ, LAMBINEN, KARHU. Side b: RAWAN, MØØN, CAT, ÇIOÜDO, ZAYANO. ' +
        'Real tesseract reads all ten with the diacritics folded away ' +
        '(JØPEZ -> "JOPEZ", ÇIOÜDO -> "CIOUDO") except one - ÇIOÜDO scored a ' +
        'genuinely low 28 confidence, still legible by eye.',
      a: ['NOKI', 'VILPERTTIS', 'JØPEZ', 'LAMBINEN', 'KARHU'],
      b: ['RAWAN', 'MØØN', 'CAT', 'ÇIOÜDO', 'ZAYANO'],
    },
  ];

  // Every frame with a panel verdict on it, witnesses included.
  function panels() {
    return PANELS
      .concat(LIVE.map(function (l) { return { file: l.file, open: l.open }; }))
      .concat(Object.keys(WITNESSES).map(function (k) {
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
      .concat(NAMEPLATES.map(function (p) { return p.file; }))
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
    LIVE: LIVE,
    NAMEPLATES: NAMEPLATES,
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
