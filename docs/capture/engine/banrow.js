// docs/capture/engine/banrow.js
// Reading the workshop's ban row off the spectator HUD.
//
// The workshop draws one text row per map (specs/2026-08-27-scrim-hero-bans-design.md):
//
//     BANS  : SOMBRA | MAUGA
//     MAP   : SAMOA
//
// Confirmed in game 2026-08-27 - a bare Hero renders as its NAME, uppercase,
// with accents and punctuation intact. heroIcon() is the thing that draws a
// glyph, and the row deliberately does not use it.
//
// The label is a TEXTUAL anchor, not a geometric one. The caller OCRs a
// generous crop of the left column and hands the whole multi-line read here;
// findRow picks the line out. That is why the crop does not have to be
// precise, and it is the difference between this and the replay-code reader,
// where a mis-placed crop yields a well-formed WRONG code and needed five
// geometry probes to catch.
//
// Nothing here touches the DOM or tesseract, so it is unit-tested directly.

(function (global) {
  'use strict';

  // refs.json writes "DVa", "Soldier 76", "Lucio", "Torbjorn"; the game draws
  // "D.VA", "SOLDIER: 76", "LÚCIO", "TORBJÖRN". Folding accents, dropping
  // punctuation and lowercasing bridges every one of them, with zero
  // collisions across all 53 catalogue names (measured, design section 4.2).
  function normalizeHeroName(s) {
    return String(s == null ? '' : s)
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '');
  }

  // Maps to the WHOLE entry, not just the guid. The role check has to run on
  // the catalogue spelling: inferRole knows "Soldier 76" and does not know
  // "SOLDIER: 76", so resolving the role from the OCR text would silently skip
  // R2 for every hero whose display name carries punctuation - D.Va, Lúcio,
  // Torbjörn, Soldier: 76 - which is exactly the set this module exists for.
  function buildHeroIndex(catalogue) {
    var index = {};
    (catalogue || []).forEach(function (h) {
      if (!h || !h.n || !h.g) return;
      var key = normalizeHeroName(h.n);
      if (key) index[key] = { g: h.g, n: h.n };
    });
    return index;
  }

  // The label may be followed by spaces before the colon, and OCR routinely
  // adds or drops one. Anchor on the word, take everything after the FIRST
  // colon - "Soldier: 76" carries one of its own, so splitting on every colon
  // would lose half the row.
  function findRow(text, label) {
    var lines = String(text == null ? '' : text).split(/[\r\n]+/);
    var wanted = normalizeHeroName(label);
    for (var i = 0; i < lines.length; i++) {
      var at = lines[i].indexOf(':');
      if (at === -1) continue;
      if (normalizeHeroName(lines[i].slice(0, at)) !== wanted) continue;
      return lines[i].slice(at + 1).trim();
    }
    // Same search again, without requiring the colon. OCR drops it: measured on
    // a real frame where the row came back as "- (R) BANS LUCIO | ANRAN" and the
    // read failed with "could not find the BANS row on screen" despite every
    // hero name being perfectly legible. The label is a TEXTUAL anchor by
    // design, so it has to survive its own punctuation going missing.
    //
    // Anchored on the first WORD rather than a prefix match, so "BANSHEE"
    // cannot stand in for "BANS"; junk before it is skipped, which is what a
    // hero icon and the crop's own edge leave behind.
    for (var j = 0; j < lines.length; j++) {
      var words = lines[j].split(/\s+/);
      for (var k = 0; k < words.length; k++) {
        var norm = normalizeHeroName(words[k]);
        if (!norm) continue;
        if (norm === wanted) return words.slice(k + 1).join(' ').trim();
        break;
      }
    }
    return null;
  }

  function fail(why) { return { ok: false, bans: [], none: false, why: why }; }

  // Validation is by SHAPE, not by OCR confidence: the workshop enforced these
  // rules, so a read that breaks one is a misread rather than an unusual scrim.
  //
  // Matching is EXACT after normalization. No edit distance, no nearest match.
  // It looks like an obvious improvement and it is not: a mis-cropped read
  // currently yields text that matches nothing and abstains, and fuzzy matching
  // would turn that safe abstention into a plausible wrong answer written into
  // a private scrim log.
  function parseBans(text, index, roleOf) {
    var row = findRow(text, 'BANS');
    if (row === null) return fail('could not find the BANS row on screen');

    if (normalizeHeroName(row) === 'none') {
      return { ok: true, bans: [], none: true, why: null };
    }

    var parts = row.split('|').map(function (p) { return p.trim(); })
      .filter(function (p) { return p.length; });
    if (parts.length !== 2) {
      return fail('expected two bans, read ' + parts.length
        + ' - a map cannot start with one, so this is a misread');
    }

    var bans = [];
    for (var i = 0; i < parts.length; i++) {
      var hit = index[normalizeHeroName(parts[i])];
      if (!hit) return fail('no hero matches "' + parts[i] + '"');
      bans.push({ g: hit.g, n: hit.n });
    }

    // roleOf sees the canonical name, so this check actually runs.
    var roleA = roleOf(bans[0].n), roleB = roleOf(bans[1].n);
    if (roleA && roleB && roleA === roleB) {
      return fail('both bans read as the ' + roleA + ' role, which the ban phase forbids');
    }
    return { ok: true, bans: bans, none: false, why: null };
  }

  var Mod = {
    normalizeHeroName: normalizeHeroName,
    buildHeroIndex: buildHeroIndex,
    findRow: findRow,
    parseBans: parseBans,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBBanRow = Mod;
})(typeof self !== 'undefined' ? self : this);
