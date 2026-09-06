// docs/capture/engine/boardreads.js
// Joining scoreboard rows to players, and turning cumulative board reads into
// per-round stats. See specs/2026-09-06-scrim-board-reads-design.md.
//
// TWO SEPARATE COORDINATE SYSTEMS MEET HERE, and confusing them is the bug this
// module exists to prevent:
//
//   - The BOARD's `team` ('a'/'b') is TEAM 1 / TEAM 2, a game concept. It is the
//     first five rows and the last five rows of the board.
//   - The BAR's `a`/`b` are the LEFT and RIGHT screen strips of portraits.
//
// Nothing in Overwatch guarantees TEAM 1 is the left strip - a spectator
// changing POV in a replay flips it - so the mapping between them is DERIVED
// from the name matches, never assumed. banrow.js hit the same wall and dodged
// it by refusing to attribute a ban to a side at all; here the names are good
// enough to resolve it, and when they are not, the module withholds the
// identity rather than guessing.
//
// The join is name-first, position-second. The design's first draft had that
// the other way round; the inversion is measured, not stylistic - the row's
// name parses reliably off the live format, whereas the positional join rests
// on the portrait bar being in slot order, which is Overwatch's HUD and is not
// verified.
//
// Works as a browser global (`window.OWDBBoardReads`) and as a CommonJS module
// for node:test.

(function (global) {
  'use strict';

  var Names = (typeof require !== 'undefined')
    ? require('./names.js')
    : global.OWDBNames;

  // The six accumulating stat columns. `x` is the role-specific sixth column,
  // deliberately unlabelled - what it means follows from the slot's hero, which
  // the comp read already knows.
  var STATS = ['k', 'd', 'dd', 'dt', 'x', 'uu'];

  // Reuse the side-detection threshold rather than inventing a second one: this
  // is the same question ("is this OCR'd name that player?") the HUD name read
  // already answers, and two thresholds would drift apart.
  var MATCH_SCORE = Names.STRONG_NAME_SCORE;

  function bestIn(name, roster) {
    var bi = -1, bs = 0;
    for (var i = 0; i < roster.length; i++) {
      var s = Names.simScore(name, roster[i]);
      if (s > bs) { bs = s; bi = i; }
    }
    return bs >= MATCH_SCORE ? { idx: bi, score: bs } : null;
  }

  // Which screen strip does this board block belong to? Whichever one its names
  // match more of. Returns null when neither strip is evidenced, which is what
  // makes "no names read" degrade to team-level stats instead of a coin-flip.
  function stripForBlock(blockNames, bar) {
    var score = { a: 0, b: 0 };
    ['a', 'b'].forEach(function (strip) {
      for (var i = 0; i < blockNames.length; i++) {
        if (bestIn(blockNames[i], bar[strip] || [])) score[strip]++;
      }
    });
    if (score.a === score.b) return null;   // no evidence, or contradictory
    return score.a > score.b ? 'a' : 'b';
  }

  // parsed: what scoreboard.js returns. bar: { a:[5 names], b:[5 names] }.
  // Returns one row per entry, always carrying team and stats; `player` and
  // `joined_by` are null wherever identity could not be established.
  function joinRows(parsed, bar) {
    var entries = (parsed && parsed.entries) || [];
    bar = bar || {};
    var roleGrouped = parsed && parsed.layout === 'role';

    var out = [];
    ['a', 'b'].forEach(function (blockTeam) {
      var block = entries.filter(function (e) { return e.team === blockTeam; });
      var names = block.map(function (e) { return e.name; });
      // A role-grouped board carries no positional meaning at all, so it gets
      // no strip and therefore no attribution - team and role only.
      var strip = roleGrouped ? null : stripForBlock(names, bar);
      var roster = (strip && bar[strip]) || [];

      block.forEach(function (e, i) {
        var row = { slot: null, team: blockTeam, player: null, joined_by: null };
        STATS.forEach(function (k) { row[k] = e[k]; });

        if (!roleGrouped) {
          var hit = e.name ? bestIn(e.name, roster) : null;
          if (hit) {
            row.slot = hit.idx;
            row.player = roster[hit.idx];
            row.joined_by = 'name';
          } else if (strip) {
            // Row i of a block IS slot i - confirmed from the mode's sort key.
            row.slot = i;
            row.player = roster[i] != null ? roster[i] : null;
            row.joined_by = row.player ? 'slot' : null;
          }
        }
        out.push(row);
      });
    });
    return out;
  }

  // ---------- deltas ----------

  function rowKey(r) {
    return r.player ? 'p:' + Names.normName(r.player) : 's:' + r.team + ':' + r.slot;
  }

  // The board accumulates over the map, so a round is the difference between
  // consecutive reads. Done HERE and not at capture time, so a fix to this
  // arithmetic applies to every capture already taken.
  function deltas(reads) {
    reads = reads || [];
    return reads.map(function (read, i) {
      var prev = i > 0 ? reads[i - 1] : null;
      var prevBy = {};
      if (prev) (prev.rows || []).forEach(function (r) { prevBy[rowKey(r)] = r; });

      var rows = (read.rows || []).map(function (r) {
        var out = { slot: r.slot, team: r.team, player: r.player, joined_by: r.joined_by };
        var base = prev ? prevBy[rowKey(r)] : null;
        STATS.forEach(function (k) {
          var cur = numeric(r[k]);
          if (cur === null) { out[k] = null; return; }
          if (!prev) { out[k] = cur; return; }
          var was = base ? numeric(base[k]) : null;
          if (was === null) { out[k] = null; return; }
          // The board only ever accumulates, so a decrease is a misread rather
          // than a real loss. Refusing it beats reporting a negative stat.
          out[k] = cur < was ? null : cur - was;
        });
        return out;
      });

      var covered = read.rounds_covered == null ? 1 : read.rounds_covered;
      // A first read that did not start from zero includes rounds nobody saw,
      // so its values are not one round's worth however tidy they look.
      var baselineOk = i > 0 || read.from_start !== false;
      return {
        round: read.round,
        match_time: read.match_time,
        rounds_covered: covered,
        attributable_to_one_round: covered === 1 && baselineOk,
        rows: rows,
      };
    });
  }

  function numeric(v) {
    if (v == null) return null;
    if (typeof v === 'number') return isFinite(v) ? v : null;
    var m = String(v).match(/-?\d+(\.\d+)?/);
    return m ? parseFloat(m[0]) : null;
  }

  // MATCH TIME is the read's identity: two reads sharing one are the same
  // moment, and storing the second would enter a zero delta as if it were a
  // round. Refused rather than stored.
  function acceptRead(existing, candidate) {
    var mt = candidate && candidate.match_time;
    if (!mt) return { ok: false, why: 'the board read carries no MATCH TIME' };
    var dupe = (existing || []).some(function (r) { return r.match_time === mt; });
    if (dupe) {
      return { ok: false, why: 'already read at MATCH TIME ' + mt
        + ' - scrub to the round boundary before reading again' };
    }
    return { ok: true, why: null };
  }

  // ---------- the whole decision, kept out of the page ----------
  //
  // scrim.html orchestrates and renders; it does not decide. Everything that
  // determines whether a read is stored, blocked or refused lives here, where
  // it can be tested without a browser, an OCR worker or a game running.

  var Board = (typeof require !== 'undefined')
    ? require('../scoreboard.js')
    : global.Scoreboard;

  // Shape validation, from the 2026-09-06 capture design adapted to the slot
  // layout. A read is accepted only if it is unambiguous: ten rows, five of
  // each team, six fields each, and at most one percentage among them.
  //
  // Nine rows is refused rather than salvaged - with one missing, nobody knows
  // WHICH is missing, and every row below the gap would attach to the wrong
  // player. That is the whole reason `fields` exists.
  function validate(parsed) {
    var e = (parsed && parsed.entries) || [];
    if (e.length !== 10) return 'the board read ' + e.length + ' rows, not 10';
    var a = e.filter(function (r) { return r.team === 'a'; }).length;
    if (a !== 5) return 'the board split ' + a + '/' + (10 - a) + ', not 5/5';
    for (var i = 0; i < e.length; i++) {
      if (e[i].fields !== 6) return 'a row came back with ' + e[i].fields + ' of 6 columns';
      var pct = 0;
      for (var j = 0; j < STATS.length; j++) {
        if (/%/.test(String(e[i][STATS[j]]))) pct++;
      }
      if (pct > 1) return 'a row carried ' + pct + ' percentages - only accuracy is one';
    }
    if (!parsed.matchTime) return 'no MATCH TIME on the board - the read has no identity';
    return null;
  }

  // status: 'ok' | 'occluded' | 'invalid' | 'duplicate'.
  // Only 'ok' carries a `read`; every other status carries a `why` the operator
  // can act on, which is the point of keeping occlusion separate from a misread.
  function evaluateRead(parsed, bar, existing, opts) {
    opts = opts || {};
    parsed = parsed || {};

    var lines = Array.isArray(parsed.raw) ? parsed.raw
      : (parsed.raw ? [String(parsed.raw)] : []);
    var occluded = Board && Board.detectOcclusion ? Board.detectOcclusion(lines) : null;
    if (occluded) return { status: 'occluded', why: occluded, read: null };

    var bad = validate(parsed);
    if (bad) return { status: 'invalid', why: bad, read: null };

    var read = {
      round: opts.round == null ? null : opts.round,
      match_time: parsed.matchTime,
      // A skip does not lose the stats, only the boundary: the next good read
      // legitimately spans the rounds either side of it and must say so.
      rounds_covered: (opts.skipped || 0) + 1,
      from_start: opts.fromStart !== false,
      layout: parsed.layout || null,
      rows: joinRows(parsed, bar),
      raw: parsed.raw || null,
    };

    var accept = acceptRead(existing, read);
    if (!accept.ok) return { status: 'duplicate', why: accept.why, read: null };
    return { status: 'ok', why: null, read: read };
  }

  var Mod = {
    STATS: STATS,
    joinRows: joinRows,
    stripForBlock: stripForBlock,
    deltas: deltas,
    acceptRead: acceptRead,
    validate: validate,
    evaluateRead: evaluateRead,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBBoardReads = Mod;
})(typeof self !== 'undefined' ? self : this);
