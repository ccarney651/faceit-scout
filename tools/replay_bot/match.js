// tools/replay_bot/match.js
// Running the shipped hero matcher headlessly.
// See specs/2026-09-08-replay-bot-design.md §3.1.
//
// docs/capture/engine/refs.js resolves REF_W/REF_H/PAD/REFS and friends as FREE
// VARIABLES rather than taking them in ctx. That is deliberate and documented in
// its own header: the two capture pages share them as page-level globals across
// refs.js, frames.js and calibration.js, the way classic <script> tags let you.
//
// Under CommonJS those free variables resolve against globalThis, so this module
// supplies them there - which is the same contract the pages honour, not a
// workaround. It is the reason the bot can run the EXACT matcher the operator
// runs instead of a reimplementation, and therefore the reason bot output can be
// compared against a human's at all.
//
// The globals are process-wide by nature. One matcher per process is the
// intended use; making two with different libraries would have them fight.

(function (global) {
  'use strict';

  var Mod = {};

  var Refs = require('../../docs/capture/engine/refs.js');
  var Util = require('../../docs/capture/engine/util.js');

  // refs.js reaches for a DOM in addRef (a learned-ref counter) and learnCrop
  // (a canvas). Neither is on the matching path, so a shim that politely finds
  // nothing is enough - and if something does start needing a real document,
  // it will fail loudly here rather than silently do half a job.
  var DOC_SHIM = {
    getElementById: function () { return null; },
    createElement: function () {
      throw new Error('match.js: refs.js asked for a canvas; matching should not need one');
    },
  };

  // Build a matcher over a parsed refs.json.
  function make(refsJson, opts) {
    var pad = (opts && opts.PAD) || 2;

    global.REF_W = refsJson.w;
    global.REF_H = refsJson.h;
    global.PAD = pad;
    global.LF = refsJson.left_fraction;
    global.TF = refsJson.top_fraction;
    global.REFS = [];
    global.LOCAL_REFS = [];
    global.CUSTOM_HEROES = {};
    global.HERO_ICON = {};

    // util.js's helpers are free variables in refs.js as well - each page
    // destructures them into page scope, and refTemplate reaches for b64bytes
    // that way. Publishing the module's whole export surface mirrors what the
    // pages do, rather than guessing which few are on the matching path.
    Object.keys(Util).forEach(function (k) { global[k] = Util[k]; });

    var R = Refs.make({ doc: DOC_SHIM });

    // refTemplate centres and L2-normalises each stored crop so bestMatch's
    // cosine similarity is comparable across the library. Using it rather than
    // recomputing means the bot's templates are built the same way the page's
    // are, down to the rounding.
    refsJson.refs.forEach(function (rec) {
      var t = R.refTemplate(rec);
      if (t) global.REFS.push(t);
    });

    // WHICH LIBRARY IS LOADED IS A GLOBAL, so a second make() re-points the
    // first handle without saying anything. Sequential use is fine and the
    // capture does it once per map; reaching for an OLDER handle afterwards is
    // the bug, and it is silent - it cost a measurement of a taught reference,
    // where "before" and "after" both read the new library and the fix looked
    // like it had done nothing. Comparing two libraries needs two processes.
    var generation = (Mod.generation = (Mod.generation || 0) + 1);

    return {
      refCount: function () { return global.REFS.length; },
      // `side` is the variant: refs are stored per side because the team-
      // coloured plate behind a portrait changes what the crop looks like.
      match: function (b64, side) {
        if (generation !== Mod.generation) {
          throw new Error('this matcher is stale: a newer matcher has replaced ' +
            'its reference library, which lives in a global. Compare two ' +
            'libraries in two processes, not two handles.');
        }
        return R.matchCrop(b64, side);
      },
    };
  }

  Mod.make = make;

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayMatch = Mod;
})(typeof globalThis !== 'undefined' ? globalThis : this);
