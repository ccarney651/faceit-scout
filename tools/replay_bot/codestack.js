// tools/replay_bot/codestack.js
// A small rotating stack of replay codes, so a code can be re-imported without
// spending a fresh one from the live league pool.
//
// WHY THE ROTATION WORKS. A league code can only be imported once - the client
// keeps a ring of its 10 most-recent imports and refuses a re-import while a
// code is still in it. Pulling from the TOP and pushing to the BOTTOM means a
// code that comes back around has had (stack size - 1) other imports happen
// since, so with ~20 codes it has been evicted from a 10-slot ring twice over
// and re-imports cleanly. See ARCHITECTURE.md §14.3b.
//
// Used by console/server.js (the manual `import` phase, and to feed run.js's
// `--code-stack` loop mode) and by run.js itself when looping.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');

  function safeCode(code) {
    var s = String(code == null ? '' : code).trim().toUpperCase();
    if (!/^[A-Z0-9]{1,12}$/.test(s)) throw new Error('bad code: ' + JSON.stringify(code));
    return s;
  }

  function load(file) {
    var raw;
    try { raw = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { return []; }
    return Array.isArray(raw.codes) ? raw.codes.map(safeCode) : [];
  }

  function save(file, codes) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify({ codes: codes.map(safeCode) }, null, 2) + '\n', 'utf8');
  }

  // Pull the top code and push it to the bottom. Returns the code, or null if
  // the stack is empty.
  function rotate(file) {
    var codes = load(file);
    if (!codes.length) return null;
    var code = codes[0];
    save(file, codes.slice(1).concat([code]));
    return code;
  }

  var Mod = { safeCode: safeCode, load: load, save: save, rotate: rotate };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCodeStack = Mod;
})(typeof self !== 'undefined' ? self : this);
