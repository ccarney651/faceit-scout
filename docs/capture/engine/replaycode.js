// docs/capture/engine/replaycode.js
// The replay code Overwatch prints on the HUD: its alphabet, where it sits on
// screen, and whether a given OCR read is a code at all.
//
// THE ALPHABET IS CROCKFORD BASE32, and that is measured, not assumed. Across
// all 4328 codes in faceit.sqlite3 (games.demo_code) every code is exactly six
// characters and only 32 distinct symbols ever appear - the ten digits plus
// A-Z without I, L, O and U - each of them 750-850 times. Zero occurrences of
// four specific characters in 25,968 draws rules out a 36-symbol alphabet.
// That set is Crockford's exactly, and 32 symbols x 6 characters is 30 bits.
//
// This matters because Crockford documents WHY those four are missing, and the
// reasons are our OCR problem: I and L "can be confused with 1", O "can be
// confused with 0". The spec then prescribes the decoder rule directly - "i and
// l will be treated as 1 and o will be treated as 0" - so the folding below is
// a published standard rather than a guess about what tesseract tends to do.
//
// U is excluded for "accidental obscenity", which has nothing to do with visual
// ambiguity, so there is no principled character to fold it to. A U therefore
// FAILS the read. An earlier draft folded it to V by inference; that was ours,
// not Crockford's, and it is exactly the kind of invention that turns a refused
// read into a wrong one.
//
// See specs/2026-08-19-replay-code-ocr-design.md.
//
// Works as a browser global (`window.OWDBReplayCode`) and as a CommonJS module
// for node:test / pytest.

(function (global) {
  'use strict';

  var ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
  var LEN = 6;

  // Crockford's decoder rule. Deliberately not a general "what OCR gets wrong"
  // table: every entry here is in the published spec.
  var FOLD = { I: '1', L: '1', O: '0' };

  // foldCode(raw) -> 'D9X9N2' | null
  //
  // Null means NO READ, and the caller must write nothing. Five good characters
  // and one unreadable is not five-sixths of a code - it is not a code, and
  // filling in the sixth would produce a record indistinguishable from a
  // correct one.
  function foldCode(raw) {
    var s = String(raw == null ? '' : raw).toUpperCase();
    // The crop carries the plate's edges, and OCR wraps legible text in
    // invented punctuation - see engine/opponents.js norm() for the same
    // finding on HUD names.
    s = s.replace(/[^A-Z0-9]/g, '');
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var ch = FOLD[s[i]] || s[i];
      if (ALPHABET.indexOf(ch) === -1) return null;
      out += ch;
    }
    return out.length === LEN ? out : null;
  }

  var Mod = { ALPHABET: ALPHABET, LEN: LEN, foldCode: foldCode };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCode = Mod;
})(typeof self !== 'undefined' ? self : this);
