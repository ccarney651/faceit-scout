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
//   <header: OWDB SCRIM <a> - <b>>          (ignored — no stat shape)
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
    // Anything that is not a letter, a digit or a percent sign is a separator.
    // The board draws U+2022 between fields and OCR renders it as whatever it
    // feels like - measured on one frame: + * = / and the guillemets - so
    // enumerating the substitutes is a losing game. Names survive because they
    // are letters and digits; the punctuation some carry is dropped, which
    // costs nothing since a name is matched fuzzily anyway. The colon stays:
    // "MATCH TIME: 9:57" needs it, and it is the one punctuation the board
    // draws deliberately.
    return line
      .replace(/[^0-9A-Za-zÀ-ɏ%:]+/g, ' ')
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
  // The digits a token STARTS with, when OCR has welded something onto the end
  // of it. The hero icon sits at the end of a row and is an image, so it comes
  // back as junk - and when that junk touches the last column the whole token
  // stops looking numeric ("0Fog"), which would drop a real value. Only used
  // once numbers have already been seen, so a name is never mistaken for one.
  function leadingNumber(tok) {
    var m = /^(\d+%?)\D/.exec(tok);
    return m ? m[1] : null;
  }

  function entryFromTokens(tokens) {
    var nums = [];
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i];
      if (looksNumeric(t)) {
        nums.push(t);
      } else {
        // Numeric columns are contiguous after the (optional) hero icon, so a
        // non-numeric token after numbers means we've hit trailing noise.
        if (nums.length) {
          var salvaged = leadingNumber(t);
          if (salvaged !== null) nums.push(salvaged);
          break;
        }
      }
    }
    // Drop a leading hero-icon token that OCR rendered as a bare number: an
    // entry always has at least K D DD DT + X + UU = 6 columns; if we see
    // exactly 7 numeric tokens the first is almost certainly the icon.
    if (nums.length === 7) nums.shift();
    if (nums.length < 4) return null;
    var x = nums.length >= 5 ? nums[4] : null;
    // The board zero-pads to hold its columns open, so "0040%" is 40% with
    // padding on it, not a different number. The zeros are a rendering detail
    // and do not belong in stored data; parseInt drops them either way.
    if (x !== null) x = x.indexOf('%') === -1 ? parseInt(x, 10) : parseInt(x, 10) + '%';
    return {
      k: parseInt(nums[0], 10),
      d: parseInt(nums[1], 10),
      dd: parseInt(nums[2], 10),
      dt: parseInt(nums[3], 10),
      x: x,
      uu: nums.length >= 6 ? parseInt(nums[5], 10) : null,
      // How many of the six columns were actually there. A row is POSITIONAL,
      // so a value that OCR dropped does not leave a hole - every later value
      // slides left into the wrong column and the row still looks plausible.
      // Measured: a "1" read as "|" costs one field and shifts the rest. The
      // count is what lets a caller refuse such a row instead of storing it.
      fields: nums.length,
    };
  }

  // The row now names its player: "{icon} {name}: {K} • {D} • ...". Everything
  // left of the first colon is the name, minus whatever the hero icon made OCR
  // emit in front of it - the character class drops that noise by keeping only
  // the trailing run of name-ish characters. The result is meant to be matched
  // FUZZILY against a known roster, not compared for equality: an icon can bleed
  // a character into it and Overwatch names carry accents and punctuation.
  function nameFromRaw(raw) {
    var i = String(raw || '').indexOf(':');
    if (i === -1) return null;
    var left = String(raw).slice(0, i);
    var m = left.match(/[A-Za-z0-9À-ɏ#_\-. ]+$/);
    var name = (m ? m[0] : left).trim();
    return name || null;
  }

  // A self-labelling row: "LEXRR  K3 D0 DMG776 TKN242 ACC50% ULT0".
  //
  // The board stopped using columns because the HUD is hostile to them - it
  // centres every line and collapses runs of spaces, so nothing can be aligned
  // except by padding with visible characters, which reads worse than the
  // problem it solves. Labelling each value instead means POSITION CARRIES NO
  // MEANING: every field is found by its own label, so a misread token damages
  // one stat rather than shifting the sense of all six, and a row that OCR
  // half-reads is honestly half-read instead of quietly wrong.
  //
  // \bD(\d+) cannot match the D of DMG, because a digit has to follow it.
  //
  // The role stat names itself - BLK, HEAL or ACC - so the row now says which
  // role it is. That used to be inferred from the legend above it, which the
  // team-grouped layouts made meaningless.
  // \s* not \s+ between K and D: OCR welds adjacent fields together, measured
  // on a real frame ("000001" from two separate columns), and "K0D0" must still
  // read as two values rather than none.
  var LABELLED = /(?:^|\s)K(\d+)\s*D(\d+)/;
  function labelledRow(raw) {
    var line = String(raw == null ? '' : raw);
    var kd = LABELLED.exec(line);
    if (!kd) return null;
    function grab(re) { var m = re.exec(line); return m ? m[1] : null; }
    // No word boundary on these: the same welding turns "DMG171 TKN169" into
    // "DMG171TKN169", where \bTKN cannot match because a digit is a word
    // character. The labels are distinctive enough to find unanchored, and that
    // is what lets a welded pair still yield BOTH values instead of neither.
    var dmg = grab(/DMG(\d+)/);
    var tkn = grab(/TKN(\d+)/);
    var ult = grab(/ULT(\d+)/);
    var special = /(BLK|HEAL|ACC)(\d+)(%?)/.exec(line);
    if (dmg === null && tkn === null && !special) return null;
    var num = function (v) { return v === null ? null : parseInt(v, 10); };
    return {
      k: num(kd[1]),
      d: num(kd[2]),
      dd: num(dmg),
      dt: num(tkn),
      x: special ? (special[3] ? parseInt(special[2], 10) + '%' : parseInt(special[2], 10)) : null,
      uu: num(ult),
      name: line.slice(0, kd.index).trim() || null,
      role: special ? ({ BLK: 'tank', HEAL: 'support', ACC: 'dps' })[special[1]] : null,
    };
  }

  // The single column header the mode now draws instead of three role legends.
  // It names no role - the sixth column varies by row - so it is recognised and
  // SKIPPED rather than pushed into roles. It carries no numbers either, so it
  // would fall out of entryFromTokens anyway; recognising it explicitly means a
  // future column rename cannot quietly turn the header into a row.
  function isColumnHeader(tokens) {
    var up = tokens.map(function (t) { return t.toUpperCase(); });
    return up.indexOf('DMG') !== -1 && up.indexOf('TKN') !== -1 && up.indexOf('ULT') !== -1;
  }

  // "TEAM 1" / "TEAM 2", the header the mode draws over each block. It replaced
  // the team COLOUR, which OCR could not see at all: the five/five split is now
  // something the parser reads rather than infers.
  function teamFromLine(tokens) {
    if (tokens.length !== 2) return null;
    if (tokens[0].toUpperCase() !== 'TEAM') return null;
    if (tokens[1] === '1') return 'a';
    if (tokens[1] === '2') return 'b';
    return null;
  }

  // Split a row into its stats and its player name. Three formats exist in the
  // wild and all three have to keep working, because a replay renders whatever
  // the mode drew on the day it was played:
  //   1. "{icon} 6 • 11 • 14861 ..."          - no name at all
  //   2. "{icon} LEXRR: 6 • 11 • ..."         - name first, briefly
  //   3. "  6 11  14861 ...  6 : LEXRR"       - name last, current
  // Which one this is follows from where the numbers are: four or more of them
  // to the LEFT of the colon means the name is on the right.
  function splitRow(raw) {
    var line = String(raw == null ? '' : raw);
    var idx = line.lastIndexOf(':');
    if (idx === -1) return { stats: line, name: null };
    var left = line.slice(0, idx);
    var right = line.slice(idx + 1).trim();
    var leftNums = tokenize(left).filter(looksNumeric).length;
    if (leftNums >= 4) return { stats: left, name: right || null };
    return { stats: line.slice(idx + 1), name: nameFromRaw(line) };
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
    // How the board is laid out, read off the board itself rather than off a
    // setting the tool cannot see. "Group by role" interleaves one legend with
    // its block, so exactly one legend precedes the first entry; the two
    // team-grouped styles stack all three legends at the top, so three do.
    var legendsBeforeFirstEntry = 0;
    var currentTeam = null;
    var sawTeamHeader = false;
    // Which entries named their own role, so the legend-era cleanup below does
    // not wipe a fact the row actually stated.
    var selfDescribed = {};

    for (var i = 0; i < lines.length; i++) {
      var raw = String(lines[i] == null ? '' : lines[i]).trim();
      if (!raw) continue;
      var tokens = tokenize(raw);
      if (!tokens.length) continue;

      var role = legendRole(tokens);
      if (role) {
        currentRole = role;
        roles.push(role);
        if (!entries.length) legendsBeforeFirstEntry++;
        continue;
      }

      if (isColumnHeader(tokens)) continue;

      var team = teamFromLine(tokens);
      if (team) {
        currentTeam = team;
        sawTeamHeader = true;
        continue;
      }

      var mt = matchTimeFromTokens(tokens, raw);
      if (mt) {
        matchTime = mt;
        continue;
      }

      // Stats never include the name: splitRow keeps them apart whichever side
      // the name is on. Without that, a name ending in a digit ("TANK 1", and
      // every bot) contributes it as a stat, and an all-digits name - which
      // Overwatch permits - is indistinguishable from one.
      // A labelled row answers everything by itself, including its role.
      var labelled = labelledRow(raw);
      if (labelled) {
        labelled.team = currentTeam;
        selfDescribed[entries.length] = true;
        entries.push(labelled);
        continue;
      }

      var parts = splitRow(raw);
      // No colon: the row leads with the player's name and then its numbers,
      // separated by bullets. Whatever sits before the first number is the
      // name - which on a board that still draws a hero icon is icon junk
      // instead, so this is matched fuzzily against a known roster downstream,
      // never trusted as an exact string.
      if (parts.name === null) {
        // Counted from the END, not the start: a row is a name followed by six
        // numbers, and taking the leading non-numeric tokens instead truncates
        // any name containing a digit after a space - every bot is called
        // "TANK 1". Real BattleTags cannot contain spaces, but the six-from-the-
        // right rule costs nothing and does not depend on that being true.
        var toks = tokenize(parts.stats);
        var end = toks.length;
        var seen = 0;
        while (end > 0 && seen < 6 && looksNumeric(toks[end - 1])) { end--; seen++; }
        if (seen === 6 && end > 0) parts.name = toks.slice(0, end).join(' ');
      }
      var entry = entryFromTokens(tokenize(parts.stats));
      if (entry) {
        entry.name = parts.name;
        entry.role = currentRole;
        entry.team = currentTeam;
        entries.push(entry);
      }
    }

    // Three legends before any entry means the rows are team-grouped, and their
    // role does NOT come from the legend above them - all three sit at the top.
    // Saying nothing is correct; the caller knows each slot's hero and can say
    // more. One legend is the role-grouped board, where the legend does label
    // its block. Anything else (the legend switched off) leaves it unknown.
    // A board that heads its blocks with TEAM 1 / TEAM 2 has said what it is;
    // nothing needs inferring from how the legends were counted.
    var layout = sawTeamHeader ? 'team'
      : legendsBeforeFirstEntry >= 3 ? 'slot'
      : legendsBeforeFirstEntry === 1 ? 'role' : null;

    // The TEAM headers are drawn in team colour now, and colour is exactly what
    // OCR loses. A full board that lost them is still a full board: ten rows in
    // team order split five and five, which is what the header would have said.
    //
    // Not on a role-grouped board, where the two teams interleave inside each
    // role block and position says nothing about side. And it fills a gap
    // rather than overriding: a team already read from a header stands.
    if (layout !== 'role' && entries.length === 10) {
      entries.forEach(function (e, i) { if (e.team == null) e.team = i < 5 ? 'a' : 'b'; });
    }
    if (layout !== 'role') {
      entries.forEach(function (e, i) { if (!selfDescribed[i]) e.role = null; });
    }

    return { roles: roles, entries: entries, matchTime: matchTime,
             layout: layout, raw: lines };
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
    nameFromRaw: nameFromRaw,
    splitRow: splitRow,
    teamFromLine: teamFromLine,
    isColumnHeader: isColumnHeader,
    leadingNumber: leadingNumber,
    labelledRow: labelledRow,
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
