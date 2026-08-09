// docs/capture/scoreboard.js
// Parser for the scrim spectator scoreboard rendered by scrim_owdb.opy
// (and by Scrimtime / DKEEH, whose layout this preserves). Pure text: it takes
// OCR'd lines from the scoreboard ROI (top-to-bottom, as tesseract returns
// them) and returns structured per-row stats.
//
// The scoreboard is a stack of Workshop HUD texts at HudPosition.LEFT, each
// SpecVisibility.ALWAYS so it shows in the spectator POV and in replays.
// sortOrder drives vertical stacking. GroupMode 0 ("Group by role, sort by
// team", the default) lays out three role blocks:
//
//   <header: OW SCOUT SCRIM <a> - <b>>          (ignored — no stat shape)
//   K • D • DD • DT • ACC • UU                  DPS legend
//   <dps entries, team1 then team2>             sortOrder 1.1 / 1.2
//   K • D • DD • DT • DB • UU                   Tank legend
//   <tank entries, team1 then team2>            sortOrder 2.1 / 2.2
//   K • D • DD • DT • HD • UU                   Support legend
//   <support entries, team1 then team2>         sortOrder 3.1 / 3.2
//   <icon> Match Time: M:SS                     sortOrder 4
//
// Entry rows (all sizes share the text):
//   "{heroIcon} {K} • {D} • {DD} • {DT} • {X} • {UU}"
// where X = round(DAMAGE_BLOCKED) for tanks, round(HEALING_DEALT) for
// supports, "{0}%".format(round(WEAPON_ACCURACY*100)) for DPS. The leading
// heroIcon is an image, so OCR may emit a stray token before the numbers; the
// parser skips leading non-numeric tokens.
//
// Works as a browser global (`window.Scoreboard`) and as a CommonJS module for
// node:test.

(function (global) {
  'use strict';

  // Legend rows are recognised by their distinctive column marker token; the
  // literal strings ACC / DB / HD never appear in entry rows (their matching
  // columns are numeric, or "NN%" for DPS accuracy).
  var LEGENDS = [
    { role: 'dps', marker: 'ACC' },
    { role: 'tank', marker: 'DB' },
    { role: 'support', marker: 'HD' },
  ];

  // Split a scoreboard line into tokens on whitespace and bullet-like
  // separators (the workshop bullet is U+2022 •; OCR often renders it as
  // '.', '|' or 'l').
  function tokenize(line) {
    return line
      .replace(/[•·|–-]+/g, ' ')
      .split(/\s+/)
      .map(function (t) { return t.trim(); })
      .filter(Boolean);
  }

  function looksNumeric(tok) {
    return /^\d+(\.\d+)?%?$/.test(tok);
  }

  // The role of a legend line, or null if the line is not a legend.
  function legendRole(tokens) {
    var upper = tokens.map(function (t) { return t.toUpperCase(); });
    for (var i = 0; i < LEGENDS.length; i++) {
      var leg = LEGENDS[i];
      var hasMarker = upper.indexOf(leg.marker) !== -1;
      // A legend is all-header text: K D DD DT <marker> UU. Guard against a
      // stray hero-icon token being uppercase text by requiring >=4 tokens
      // and no numeric tokens.
      if (hasMarker && tokens.length >= 4 && !tokens.some(looksNumeric)) {
        return leg.role;
      }
    }
    return null;
  }

  // Parse an entry row into {k,d,dd,dt,x,uu}; x keeps its '%' when present.
  // Returns null if the row is not an entry (too few numeric columns).
  function entryFromTokens(tokens) {
    var nums = [];
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (looksNumeric(t)) {
        nums.push(t);
      } else {
        // Numeric columns are contiguous after the (optional) hero icon, so a
        // non-numeric token after numbers means we've hit trailing noise.
        if (nums.length) break;
      }
    }
    // Drop a leading hero-icon token that OCR rendered as a bare number: an
    // entry always has at least K D DD DT + X + UU = 6 columns; if we see
    // exactly 7 numeric tokens the first is almost certainly the icon.
    if (nums.length === 7) nums.shift();
    if (nums.length < 4) return null;
    var x = nums.length >= 5 ? nums[4] : null;
    if (x !== null && x.indexOf('%') === -1) x = parseInt(x, 10);
    return {
      k: parseInt(nums[0], 10),
      d: parseInt(nums[1], 10),
      dd: parseInt(nums[2], 10),
      dt: parseInt(nums[3], 10),
      x: x,
      uu: nums.length >= 6 ? parseInt(nums[5], 10) : null,
    };
  }

  function matchTimeFromTokens(tokens, raw) {
    var joined = tokens.join(' ').toLowerCase();
    if (joined.indexOf('match time') === -1) {
      // Fall back to a bare M:SS token on a line that also mentions time.
      if (!/time/.test(joined) && !/^\d{1,3}:\d{2}$/.test(raw)) return null;
    }
    for (var i = 0; i < tokens.length; i++) {
      var m = /^(\d{1,3}):(\d{2})$/.exec(tokens[i]);
      if (m) return m[1] + ':' + m[2];
    }
    return null;
  }

  // Parse the top-centre score readout box (a small "a - b" readout, e.g.
  // "2 - 3"). Returns {a, b} or null. Uses the last two numeric tokens so a
  // leading icon/label is ignored.
  function parseScoreReadout(raw) {
    var tokens = tokenize(String(raw || '').trim());
    var nums = tokens.filter(looksNumeric);
    if (nums.length < 2) return null;
    return { a: parseInt(nums[nums.length - 2], 10), b: parseInt(nums[nums.length - 1], 10) };
  }

  // Main entry point. lines: array of OCR'd strings, top-to-bottom.
  // Returns { roles:[...], entries:[...], matchTime, raw }.
  function parse(lines) {
    var roles = [];
    var entries = [];
    var matchTime = null;
    var currentRole = null;

    for (var i = 0; i < lines.length; i++) {
      var raw = String(lines[i] == null ? '' : lines[i]).trim();
      if (!raw) continue;
      var tokens = tokenize(raw);
      if (!tokens.length) continue;

      var role = legendRole(tokens);
      if (role) {
        currentRole = role;
        roles.push(role);
        continue;
      }

      var mt = matchTimeFromTokens(tokens, raw);
      if (mt) {
        matchTime = mt;
        continue;
      }

      var entry = entryFromTokens(tokens);
      if (entry && currentRole) {
        entry.role = currentRole;
        entries.push(entry);
      }
    }

    return { roles: roles, entries: entries, matchTime: matchTime, raw: lines };
  }

  // Best-effort team split: within each role block, GroupMode 0 stacks team1
  // entries above team2 (sortOrder .1 then .2). Given a per-team count for the
  // role (from the live portrait strips, typically 1 tank / 2 dps / 2 support
  // per team), the first N entries of the block are team 'a', the rest 'b'.
  // Sets `entry.team` in place; entries that can't be split confidently get
  // `team: null`.
  function assignTeams(result, perTeamRoleCounts) {
    var byRole = {};
    result.entries.forEach(function (e) {
      (byRole[e.role] = byRole[e.role] || []).push(e);
    });
    Object.keys(byRole).forEach(function (role) {
      var list = byRole[role];
      var perTeam = perTeamRoleCounts && perTeamRoleCounts[role];
      if (!perTeam || list.length !== perTeam * 2) {
        list.forEach(function (e) { e.team = null; });
        return;
      }
      list.forEach(function (e, idx) { e.team = idx < perTeam ? 'a' : 'b'; });
    });
    return result;
  }

  var Scoreboard = {
    tokenize: tokenize,
    parse: parse,
    parseScoreReadout: parseScoreReadout,
    assignTeams: assignTeams,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Scoreboard;
  } else {
    global.Scoreboard = Scoreboard;
  }
})(typeof self !== 'undefined' ? self : this);
