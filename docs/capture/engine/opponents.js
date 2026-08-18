// docs/capture/engine/opponents.js
// Who are we scrimming? Identifies the two sides of a scrim from the ten player
// names read off the HUD — see specs/2026-08-12-scrim-mode-design.md §4.2-4.3.
//
// Scrim partners are not limited to one division, one region, or even to real
// teams: a "mix" of five unaffiliated players is a normal opponent. So this
// answers three questions in order, and never blocks capture on any of them:
//
//   1. Which side are WE on?            (match against our own roster)
//   2. Is the other side a league team? (match against every team's roster)
//   3. Have we played them before?      (match against locally-remembered groups)
//
// A side nobody recognises is simply "Opponent". That is a valid answer, not a
// failure, and the capture proceeds either way.
//
// THE BAR IS THREE OF FIVE, and that is measured, not guessed. Players show up
// to scrims on smurf accounts constantly, so demanding five would push the
// common case back into manual typing. Against 8356 real five-player lineups
// and 159 teams (tools/roster_match_eval.py): 3-of-5 identifies 99.9% uniquely
// and correctly, 0.1% ambiguously, and NONE wrongly; the tie-break below
// resolves every ambiguous case. With smurfs substituted in, one or two still
// identify 100% correctly and three falls back to "Opponent" rather than to a
// wrong team — arithmetic, since three smurfs leaves only two known names.
//
// Works as a browser global (`window.OWDBOpponents`) and as a CommonJS module.

(function (global) {
  'use strict';

  var MIN_MATCHES = 3;          // of five. See the header - measured, not guessed.

  // Names arrive from OCR and from a database that stores them without a
  // discriminator, so both sides are folded the same way before comparison.
  // Mirrors OWDBNames.normName; duplicated deliberately so this module stays
  // usable on its own under node:test without wiring up names.js.
  // Battle.net names carry a #1234 discriminator; everything after it is noise.
  // Punctuation goes too: OCR wraps a perfectly legible name in whatever it
  // made of the plate edges - "§ ASHBORN |}" is ASHBORN, and comparing it
  // as a whole string is how a clean read matched nothing.
  function norm(name) {
    var s = String(name == null ? '' : name).trim().toLowerCase();
    var hash = s.indexOf('#');
    if (hash !== -1) s = s.slice(0, hash);
    return s.replace(/[^a-z0-9]/g, '');
  }

  // Minimum length for a fragment to be treated as a name in its own right.
  // Three, because the shortest real name met in the field is NUT - and
  // because one- and two-character fragments are exactly what OCR invents.
  var MIN_TOKEN = 3;

  // Every string a read could reasonably BE: the whole thing stripped, plus
  // each whitespace-separated fragment. "i XYPHER |" normalises whole to
  // "ixypher", which matches nothing - the stray letter has to be allowed to
  // fall away without taking the name with it. Roster names are put through
  // the same expansion, so the comparison stays symmetric.
  function normSet(names) {
    var out = [];
    function push(k) { if (k && out.indexOf(k) === -1) out.push(k); }
    (names || []).forEach(function (n) {
      push(norm(n));
      String(n == null ? '' : n).split(/\s+/).forEach(function (part) {
        var k = norm(part);
        if (k.length >= MIN_TOKEN) push(k);
      });
    });
    return out;
  }

  // buildTeamIndex(data) — from data.json's `team_rosters` (every team's
  // accumulated squad). Falls back to the per-match `rosters` map when
  // team_rosters is absent, so an older feed still identifies the teams it can
  // rather than nothing at all.
  function buildTeamIndex(data) {
    var d = data || {};
    var index = [];
    var byId = {};

    function add(teamId, name, players) {
      if (!teamId) return;
      var slot = byId[teamId];
      if (!slot) {
        slot = byId[teamId] = { team_id: teamId, name: name || null, names: [] };
        index.push(slot);
      }
      if (!slot.name && name) slot.name = name;
      (players || []).forEach(function (p) {
        var k = norm(p && (p.game_name || p.nick));
        if (k && slot.names.indexOf(k) === -1) slot.names.push(k);
      });
    }

    var tr = d.team_rosters;
    if (tr) {
      Object.keys(tr).forEach(function (tid) { add(tid, tr[tid].name, tr[tid].players); });
    }
    // Older feeds, and any team present only in a coded match.
    var per = d.rosters || {};
    Object.keys(per).forEach(function (mid) {
      var m = per[mid] || {};
      Object.keys(m).forEach(function (tid) { add(tid, m[tid].name, m[tid].players); });
    });
    return index;
  }

  // score(seen, index) — every candidate that clears the bar, best first.
  function score(seen, index) {
    var names = normSet(seen);
    var hits = [];
    (index || []).forEach(function (t) {
      var n = 0;
      for (var i = 0; i < names.length; i++) if (t.names.indexOf(names[i]) !== -1) n++;
      if (n >= MIN_MATCHES) hits.push({ team_id: t.team_id, name: t.name, matched: n });
    });
    hits.sort(function (a, b) { return b.matched - a.matched; });
    return hits;
  }

  // identifyTeam(seen, index) — the one team these names belong to, or null.
  //
  // Tie-break, which the three-of-five bar makes reachable: most overlap wins;
  // a genuine tie assigns NOBODY and returns the candidates instead. Guessing
  // between two teams would attribute someone else's comps to them, which is
  // worse than leaving it as "Opponent".
  function identifyTeam(seen, index) {
    var hits = score(seen, index);
    if (!hits.length) return null;
    var top = hits[0].matched;
    var winners = hits.filter(function (h) { return h.matched === top; });
    if (winners.length > 1) {
      return { team_id: null, name: null, matched: top, ambiguous: true, candidates: winners };
    }
    return {
      team_id: winners[0].team_id, name: winners[0].name,
      matched: top, ambiguous: false,
      // Below five, some of the five were not recognised - very likely smurfs,
      // which §4.3 learns as aliases so the same lineup identifies outright
      // next time.
      unmatched: normSet(seen).filter(function (n) {
        var t = null;
        for (var i = 0; i < index.length; i++) if (index[i].team_id === winners[0].team_id) { t = index[i]; break; }
        return t ? t.names.indexOf(n) === -1 : true;
      }),
    };
  }

  // --- local opponent registry --------------------------------------------
  // Groups we have scrimmed that are not league teams: mixes, teams from other
  // regions or tournaments. Keyed on the name-set, since that is all we have.

  // A stored group matches when at least MIN_MATCHES of the incoming five are
  // already known for it - the same tolerance, for the same reason (a
  // substitute or one OCR miss must not create a duplicate group).
  function findLocalGroup(seen, groups) {
    var names = normSet(seen);
    var best = null;
    (groups || []).forEach(function (g) {
      var n = 0;
      var known = normSet(g.roster_names);
      for (var i = 0; i < names.length; i++) if (known.indexOf(names[i]) !== -1) n++;
      if (n >= MIN_MATCHES && (!best || n > best.matched)) best = { group: g, matched: n };
    });
    return best;
  }

  // Absorb any names this group has not seen before. A stand-in today is a
  // recognised member tomorrow, which is what keeps a recurring practice
  // partner identifiable as its lineup drifts.
  function mergeIntoGroup(group, seen) {
    var known = normSet(group.roster_names);
    normSet(seen).forEach(function (n) { if (known.indexOf(n) === -1) known.push(n); });
    group.roster_names = known;
    group.times_played = (group.times_played || 0) + 1;
    return group;
  }

  function newLocalGroup(seen, now) {
    return {
      id: 'opp-' + (now || Date.now()).toString(36) + Math.random().toString(36).slice(2, 7),
      kind: 'local_group',
      team_id: null,
      label: null,                       // named later, or never
      roster_names: normSet(seen),
      first_seen: new Date(now || Date.now()).toISOString(),
      times_played: 1,
    };
  }

  // --- smurf aliases -------------------------------------------------------
  // Names that did not match, on an identification the operator did not
  // correct, are very likely that team's alt accounts. Learning them widens the
  // roster so the same lineup identifies outright next time - the measured
  // reason three smurfs currently fall back to "Opponent".
  //
  // Two safeguards, because this writes identity data by itself: it only runs
  // on an uncorrected identification (the caller's job), and aliases stay local
  // and are never included in a shared scout, which would leak the mapping
  // between a player's main and their alts.
  function learnAliases(aliasStore, teamId, unmatched) {
    if (!teamId) return aliasStore;
    var store = aliasStore || {};
    var have = store[teamId] || [];
    normSet(unmatched).forEach(function (n) { if (have.indexOf(n) === -1) have.push(n); });
    store[teamId] = have;
    return store;
  }

  // An index with learned aliases folded in, so identification improves with
  // use. Does not mutate the index it is given.
  function indexWithAliases(index, aliasStore) {
    var store = aliasStore || {};
    return (index || []).map(function (t) {
      var extra = store[t.team_id] || [];
      if (!extra.length) return t;
      var names = t.names.slice();
      extra.forEach(function (n) { if (names.indexOf(n) === -1) names.push(n); });
      return { team_id: t.team_id, name: t.name, names: names };
    });
  }

  // --- sides ---------------------------------------------------------------
  // Which HUD side are we on? Answered from our own roster, so the operator
  // stops setting it by hand. Null means unknown - the caller keeps the manual
  // control rather than guessing.
  function ourSide(leftNames, rightNames, ourRoster) {
    var ours = normSet(ourRoster);
    if (ours.length < MIN_MATCHES) return null;
    function overlap(names) {
      var n = 0, k = normSet(names);
      for (var i = 0; i < k.length; i++) if (ours.indexOf(k[i]) !== -1) n++;
      return n;
    }
    var l = overlap(leftNames), r = overlap(rightNames);
    if (l >= MIN_MATCHES && l > r) return 'left';
    if (r >= MIN_MATCHES && r > l) return 'right';
    return null;                      // both or neither - do not guess
  }

  var Opponents = {
    MIN_MATCHES: MIN_MATCHES,
    norm: norm,
    normSet: normSet,
    buildTeamIndex: buildTeamIndex,
    score: score,
    identifyTeam: identifyTeam,
    findLocalGroup: findLocalGroup,
    mergeIntoGroup: mergeIntoGroup,
    newLocalGroup: newLocalGroup,
    learnAliases: learnAliases,
    indexWithAliases: indexWithAliases,
    ourSide: ourSide,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Opponents;
  else global.OWDBOpponents = Opponents;
})(typeof self !== 'undefined' ? self : this);
