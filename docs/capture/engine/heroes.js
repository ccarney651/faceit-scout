// docs/capture/engine/heroes.js
// Which role each hero plays, and how to group a hero catalogue by it.
//
// The authoritative seats live in faceit_sync/subroles.py. Neither page that
// needs this table has a build step, so a copy is unavoidable - but there is
// now exactly ONE copy, and tests/test_scrims_viewer.py fails if it disagrees
// with subroles.py. It was two copies for about an hour during the panel ban
// picker's design, and the reason it is not is that the first copy had already
// drifted silently: "D.Va", "Soldier: 76" and "Lifeweaver" are display
// spellings refs.json never writes, so those heroes matched nothing and fell
// out of every role split, and ten 2026 heroes were missing outright.
//
// The three roles here are subroles.py's five seats collapsed - Hitscan and
// Flex DPS are both Damage, Main and Flex Support are both Support - because
// role lock is what the game enforces and what a ban picker groups by.
//
// Consumers: docs/scrims.html (role splits in the analysis) and
// docs/capture/scrim.html (the panel's ban picker). Adding a hero to the game
// means adding it here, and this file is one of the places AGENTS.md lists.
//
// Works as a browser global (`window.OWDBHeroes`) and as a CommonJS module for
// node:test / pytest.

(function (global) {
  'use strict';

  var ROLE_MAP = {
    tank: ['D.Mon', 'DVa', 'Domina', 'Doomfist', 'Hazard', 'Junker Queen', 'Mauga', 'Orisa', 'Ramattra', 'Reinhardt', 'Roadhog', 'Sigma', 'Winston', 'Wrecking Ball', 'Zarya'],
    damage: ['Anran', 'Ashe', 'Bastion', 'Cassidy', 'Echo', 'Emre', 'Freja', 'Genji', 'Hanzo', 'Junkrat', 'Mei', 'Pharah', 'Reaper', 'Shion', 'Sierra', 'Sojourn', 'Soldier 76', 'Sombra', 'Symmetra', 'Torbjorn', 'Tracer', 'Vendetta', 'Venture', 'Widowmaker'],
    support: ['Ana', 'Baptiste', 'Brigitte', 'Illari', 'Jetpack Cat', 'Juno', 'Kiriko', 'LifeWeaver', 'Lucio', 'Mercy', 'Mizuki', 'Moira', 'Wuyang', 'Zenyatta'],
  };

  // Tank / Damage / Support, in the order the game lists them - which is the
  // order the operator's eye already expects from the hero select screen.
  var ROLE_ORDER = ['Tank', 'Damage', 'Support'];

  function inferRole(name) {
    if (!name) return null;
    var n = String(name).toLowerCase();
    for (var role in ROLE_MAP) {
      for (var i = 0; i < ROLE_MAP[role].length; i++) {
        if (ROLE_MAP[role][i].toLowerCase() === n) return role.charAt(0).toUpperCase() + role.slice(1);
      }
    }
    return null;
  }

  // byRole(catalogue) — [{role, heroes:[{g,n}]}], role blocks in play order and
  // heroes alphabetical inside each. Takes the catalogue rather than reading a
  // global so the custom heroes an operator has taught this browser are grouped
  // alongside the built-in ones.
  //
  // A hero with no known role goes to "Other" rather than being dropped: an
  // unrecognised hero is one the table has not caught up with, and making it
  // unbannable would be a worse answer than putting it in a group of its own.
  // An empty role block is omitted entirely - a heading with nothing under it
  // is just noise in a panel this small.
  function byRole(catalogue) {
    var bins = {};
    (catalogue || []).forEach(function (h) {
      var role = inferRole(h && h.n) || 'Other';
      (bins[role] = bins[role] || []).push(h);
    });
    return ROLE_ORDER.concat(['Other']).filter(function (r) { return bins[r] && bins[r].length; })
      .map(function (r) {
        return {
          role: r,
          heroes: bins[r].slice().sort(function (a, b) { return String(a.n || '').localeCompare(String(b.n || '')); }),
        };
      });
  }

  var Mod = {
    ROLE_MAP: ROLE_MAP,
    ROLE_ORDER: ROLE_ORDER,
    inferRole: inferRole,
    byRole: byRole,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBHeroes = Mod;
})(typeof self !== 'undefined' ? self : this);
