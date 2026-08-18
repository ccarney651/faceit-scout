// docs/capture/engine/names.js
// Player-name similarity helpers shared by index.html and scrim.html: a
// browser port of the .exe's confident_left_faction (owdb/capture.py) that
// fuzzy-matches OCR'd HUD name strips against known rosters so a side/player
// can be tagged only when the read is unambiguous.
//
// Reconciled from the two hand-maintained forks (see
// tools/capture_divergence.py): _matchTotal, affinity and confidentOrientation
// were identical between the pages. simScore had drifted — index.html
// normalised through _normName() (folds accents) before comparing, scrim.html
// only lowercased and trimmed. index.html's version was kept, since it is the
// stronger normaliser and phase 2 aims this function at battletag matching.
//
// normName also now strips a `#` discriminator: the ready-up list renders the
// real battletag (e.g. "Kirbz#2183"), but stored game_name values carry no
// discriminator, so both forms must compare equal.
//
// Works as a browser global (`window.OWDBNames`) and as a CommonJS module for
// node:test / pytest.

(function (global) {
  'use strict';

  // MIN_STRONG_NAMES is lower here (2, vs the exe's 3) — a deliberate,
  // browser-only divergence. The exe's thresholds were measured against
  // Windows' native OCR on dxcam frames (owdb/capture.py: good reads cleared
  // 5-6 strong names, a known-garbage misaligned frame scored 0). tesseract.js
  // reading a getDisplayMedia canvas is a weaker OCR engine on a lossier
  // source, and field use since the auto-detect-on-Snapshot gate shipped
  // (2026-07-31) put its real hit rate around 70% at MIN_STRONG_NAMES=3 —
  // clearing snapshots often enough to be reliable, but failing (and blocking
  // capture entirely, since this gate is now mandatory) often enough to be
  // frustrating. Dropping to 2 is the single most targeted loosening: it only
  // lowers how many individually-strong reads are required, not the
  // match-quality bar (STRONG_NAME_SCORE) or the aggregate-lead bar
  // (AUTO_SIDE_MARGIN, the stronger anti-noise gate — it alone would already
  // reject the exe's documented garbage case, margin 25 vs this 100
  // threshold).
  var AUTO_SIDE_MARGIN = 100, STRONG_NAME_SCORE = 75, MIN_STRONG_NAMES = 2;

  // difflib.SequenceMatcher.ratio() = 2*M/(len a+len b), M = total size of the
  // longest matching blocks (Ratcliff/Obershelp). Names are short → skip junk.
  function _matchTotal(a, ai, aj, b, bi, bj) {
    var besti = ai, bestj = bi, best = 0, j2 = {};
    for (var i = ai; i < aj; i++) {
      var nj = {};
      for (var j = bi; j < bj; j++) {
        if (a[i] === b[j]) {
          var k = (j2[j - 1] || 0) + 1; nj[j] = k;
          if (k > best) { besti = i - k + 1; bestj = j - k + 1; best = k; }
        }
      }
      j2 = nj;
    }
    var tot = best;
    if (best) {
      tot += _matchTotal(a, ai, besti, b, bi, bestj);
      tot += _matchTotal(a, besti + best, aj, b, bestj + best, bj);
    }
    return tot;
  }

  // Latin letters with a STROKE or BAR rather than a combining accent. NFD only
  // decomposes what has a canonical decomposition, and these have none - so the
  // fold below left them untouched while OCR, restricted to ASCII, can only ever
  // emit the base letter. The roster kept "słøw" while a *perfect* read said
  // "slow", scoring 50 against a bar of 75: a name that could never match no
  // matter how good the OCR got. Affects 10 of 1304 league players (measured by
  // tools/assign_eval.py); see specs/2026-08-16-player-assignment-design.md 4.4.
  var STROKED = {
    'ø': 'o', 'ł': 'l', 'đ': 'd', 'ħ': 'h', 'ŧ': 't', 'ŋ': 'n', 'ɓ': 'b',
    'ƒ': 'f', 'ŀ': 'l', 'ɛ': 'e', 'ɠ': 'g', 'ƕ': 'h', 'ǂ': 't', 'ǃ': '!',
    'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'þ': 'p', 'ð': 'd', 'ı': 'i', 'ſ': 's',
  };

  // Fold accents before comparing: the HUD renders the real Battle.net name
  // (e.g. "Hēv"), but tessedit_char_whitelist is plain ASCII, so OCR can only
  // ever return "Hev" - without this, an otherwise-perfect read scores as a
  // near-miss purely because of a diacritic it was never allowed to emit.
  // Also drops everything from the first '#' onward, so a ready-up battletag
  // ("Kirbz#2183") compares equal to the stored game_name ("Kirbz").
  function normName(s) {
    var str = String(s == null ? '' : s);
    var hashIdx = str.indexOf('#');
    if (hashIdx !== -1) str = str.slice(0, hashIdx);
    str = str.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    // After the accent fold, so a lower-cased stroked letter is what we look up.
    var out = '';
    for (var i = 0; i < str.length; i++) {
      var ch = str.charAt(i);
      out += (STROKED[ch] !== undefined) ? STROKED[ch] : ch;
    }
    return out;
  }

  function simScore(a, b) {
    a = normName(a); b = normName(b);
    var L = a.length + b.length; if (!L) return 0;
    return 200 * _matchTotal(a, 0, a.length, b, 0, b.length) / L; // 0..100
  }

  function affinity(names, roster) {
    var s = 0;
    for (var i = 0; i < names.length; i++) {
      var n = names[i]; if (!n) continue;
      var best = 0;
      for (var j = 0; j < roster.length; j++) best = Math.max(best, simScore(n, roster[j]));
      s += best;
    }
    return s;
  }

  // Which faction is on the LEFT HUD strip: 'a', 'b', or null when unclear.
  function confidentOrientation(leftNames, rightNames, aRoster, bRoster) {
    var direct = affinity(leftNames, aRoster) + affinity(rightNames, bRoster);
    var swap = affinity(leftNames, bRoster) + affinity(rightNames, aRoster);
    var got, lead, rosters;
    if (direct >= swap) { got = 'a'; lead = direct - swap; rosters = [aRoster, bRoster]; }
    else { got = 'b'; lead = swap - direct; rosters = [bRoster, aRoster]; }
    if (lead < AUTO_SIDE_MARGIN) return null;
    var strong = 0; var sides = [leftNames, rightNames];
    for (var k = 0; k < 2; k++) {
      for (var i = 0; i < sides[k].length; i++) {
        var n = sides[k][i]; if (!n) continue;
        var best = 0;
        for (var j = 0; j < rosters[k].length; j++) best = Math.max(best, simScore(n, rosters[k][j]));
        if (best >= STRONG_NAME_SCORE) strong++;
      }
    }
    return strong >= MIN_STRONG_NAMES ? got : null;
  }

  var Mod = {
    normName: normName,
    simScore: simScore,
    affinity: affinity,
    confidentOrientation: confidentOrientation,
    AUTO_SIDE_MARGIN: AUTO_SIDE_MARGIN,
    STRONG_NAME_SCORE: STRONG_NAME_SCORE,
    MIN_STRONG_NAMES: MIN_STRONG_NAMES,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBNames = Mod;
})(typeof self !== 'undefined' ? self : this);
