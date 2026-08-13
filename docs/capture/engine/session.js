// docs/capture/engine/session.js
// Scrim session scaffolding: the league-code block and the replay-code
// wipe check.
//
// The league-code block is a correctness guarantee, not a convenience. The
// scrim page's help text has always claimed league codes are blocked while no
// code implemented it; a league map recorded as a scrim would stay private in
// one person's browser instead of being published to the site.
//
// Replay codes are invalidated by every Overwatch patch (a "code wipe"). The
// date has one source - _SEED_WIPES in owdb/db.py - and reaches the browser as
// data.json's code_wipe_date.

(function (global) {
  'use strict';

  function norm(code) {
    return String(code == null ? '' : code).trim().toUpperCase();
  }

  function buildCodeIndex(data) {
    var d = data || {};
    var codes = new Set();
    var byCode = {};
    (d.codes || []).forEach(function (c) {
      if (!c || !c.code) return;
      var k = norm(c.code);
      codes.add(k);
      byCode[k] = c;
    });
    return { codes: codes, byCode: byCode, wipeDate: d.code_wipe_date || null };
  }

  // played: ISO date (YYYY-MM-DD) the map was played, i.e. the session date.
  function classifyCode(code, index, played) {
    var k = norm(code);
    var entry = index.byCode[k] || null;
    var dead = false;
    if (index.wipeDate && played) {
      dead = String(played) < String(index.wipeDate);
    }
    return {
      league: index.codes.has(k),
      dead: dead,
      division: entry ? (entry.division || null) : null,
    };
  }

  // Does the parsed score contradict the parsed result? OCR reads the result
  // word far more reliably than the digits - "VICTORY" survives damage that
  // turns "2 - 0" into "2 - ©", which the parser then reports as a confident
  // 0-0. Observed in a real run against a rendered replay history. The row is
  // still worth keeping (its map and code are the point), but the score must
  // be shown as suspect rather than as fact.
  function scoreDisagreesWithResult(result, score) {
    if (!result || !score) return false;
    var us = score.us, them = score.them;
    if (us === 0 && them === 0) return true;          // no score survived at all
    if (result === 'win') return !(us > them);
    if (result === 'loss') return !(us < them);
    if (result === 'draw') return us !== them;
    return false;
  }

  function buildScaffold(rows, index, played) {
    return (rows || []).map(function (r) {
      var cls = r.code ? classifyCode(r.code, index, played)
                       : { league: false, dead: false, division: null };
      var score = r.score || { us: 0, them: 0 };
      return {
        map_name: r.map_name,
        map_category: r.map_category,
        code: r.code || null,
        score: score,
        result: r.result || null,
        score_suspect: scoreDisagreesWithResult(r.result || null, score),
        league: cls.league,
        dead: cls.dead,
        division: cls.division,
      };
    });
  }

  var Session = {
    norm: norm,
    buildCodeIndex: buildCodeIndex,
    classifyCode: classifyCode,
    buildScaffold: buildScaffold,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Session;
  else global.OWDBSession = Session;
})(typeof self !== 'undefined' ? self : this);
