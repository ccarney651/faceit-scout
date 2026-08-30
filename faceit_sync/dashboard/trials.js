/* ---------- trialist comparison: the local tool's whole UI ----------
   Runs on top of pure.js, which is inlined ahead of it unchanged. Every rate,
   record and z-score on this page comes from there — playerSeason(),
   efficiencyRatings(), playerRate() — so a number here and the same number on
   owdb.io cannot disagree.

   Not part of the dashboard: faceit_sync/_dashboard.py::_PARTS names its parts
   explicitly, and this file is not one of them. */

const DATA = window.__OWDB_DATA__ || {};
const IDX = window.__TRIALS_INDEX__ || [];
const DIVS = DATA.divisions || {};
const COMPS = DATA.owdb_comps || {};
const PERGAME = DATA.owdb_pergame_players || {};

const POOL_KEY = 'owdb-trials-pool';
const TABLE_ORDER = ['Tank', 'Damage', 'Support', 'Unassigned'];
const BY_NICK = {};
IDX.forEach(function (e) { BY_NICK[e.nick] = e; });

let POOL = loadPool();
let STORAGE_OK = true;

function loadPool() {
  try {
    const v = JSON.parse(localStorage.getItem(POOL_KEY) || '[]');
    return Array.isArray(v) ? v.filter(function (n) { return typeof n === 'string'; }) : [];
  } catch (e) { STORAGE_OK = false; return []; }
}
function savePool() {
  try { localStorage.setItem(POOL_KEY, JSON.stringify(POOL)); }
  catch (e) { STORAGE_OK = false; }
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}
function el(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
function nf(n) { return n == null ? '—' : Number(n).toLocaleString('en-GB'); }
function dshort(iso) { return iso ? String(iso).slice(0, 10) : '—'; }

/* ---- Eff cohorts -----------------------------------------------------------
   Copied from app.js (roleOf / ROLE_SEATS / seatOfPlayer / effGroupOf /
   playerCaptures) rather than approximated, so the peer group here is the same
   peer group the site uses. Only the cohort assignment is duplicated; the rating
   itself is pure.js's efficiencyRatings(). If app.js's version changes, this
   one has to follow — the two are a knowing fork, kept small on purpose. */
const HERO_SEAT = {};
(DATA.heroes || []).forEach(function (h) { if (h.subrole) HERO_SEAT[h.name] = h.subrole; });
const ROLE_SEATS = { Damage: ['Hitscan', 'Flex DPS'], Support: ['Main Support', 'Flex Support'] };
const roleOf = function (r) {
  return /tank/i.test(r || '') ? 'Tank'
    : /support/i.test(r || '') ? 'Support'
      : /dam|dps/i.test(r || '') ? 'Damage' : null;
};
function seatOfPlayer(p) {
  const role = roleOf(p.role); if (!role) return null;
  const hs = (p.cap && p.cap.heroes) || []; if (!hs.length) return null;
  if (role === 'Tank') return 'Tank';
  const allowed = ROLE_SEATS[role]; if (!allowed) return null;
  const tally = {};
  hs.forEach(function (h) {
    const s = HERO_SEAT[h.hero];
    if (s && allowed.indexOf(s) >= 0) tally[s] = (tally[s] || 0) + (h.rounds || 0);
  });
  return Object.keys(tally).sort(function (a, b) { return tally[b] - tally[a]; })[0] || allowed[0];
}
function effGroupOf(p) { const seat = seatOfPlayer(p); return seat || roleOf(p.role) || null; }

function capturesFor(cid) {
  const div = DIVS[cid] || {}, out = {};
  (div.team_names || []).forEach(function (team) {
    ((((COMPS[team] || {}).scout || {}).players) || []).forEach(function (p) {
      out[team + '|' + p.player] = { rounds: p.rounds || 0, heroes: (p.heroes || []).slice() };
    });
  });
  return out;
}
// A player's Eff inside one division, built from that division's whole cohort.
// An Eff is a comparison, so it cannot be computed for one player alone — and
// certainly not against the trialist pool, which is not a peer group.
function effFor(nick, cid) {
  const div = cid ? DIVS[cid] : null;
  if (!div) return null;
  const cap = capturesFor(cid), list = [];
  (div.teams || []).forEach(function (t) {
    (t.roster || []).forEach(function (p) {
      list.push({
        nick: p.nick, role: p.role || '', stats: p.stats || null,
        cap: cap[t.name + '|' + p.nick] || null
      });
    });
  });
  const effs = efficiencyRatings(list.map(function (p) {
    return { group: effGroupOf(p), stats: p.stats };
  }));
  const i = list.findIndex(function (p) { return p.nick === nick; });
  return i >= 0 ? effs[i] : null;
}

/* ---- per-player facts ----------------------------------------------------- */
function factsFor(nick) {
  const S = playerSeason(nick, DIVS, COMPS, PERGAME);
  const idx = BY_NICK[nick] || {};
  const cur = S.current;
  // The division they are in NOW, not the one with the most maps: a player who
  // moved up mid-season has a stale elo and a stale peer group in the old one.
  const d0 = (cur && S.divisions.find(function (d) { return d.cid === cur.cid; })) || S.divisions[0] || {};
  const games = S.maps.reduce(function (a, m) { return a + m.games; }, 0);
  const wins = S.maps.reduce(function (a, m) { return a + m.wins; }, 0);
  return {
    nick: nick, idx: idx, S: S, cur: cur, d0: d0,
    found: S.found, games: games, wins: wins,
    wr: games ? Math.round(100 * wins / games) : null,
    stats: d0.stats || null,
    eff: effFor(nick, d0.cid)
  };
}

function rateCell(wr, n, floor, label) {
  if (wr == null) {
    return '<span class="faint" title="' + esc(label) + ' needs ' + floor +
      '+ games; ' + n + ' so far">—</span>';
  }
  const cls = wr >= 60 ? 'good' : wr >= 45 ? 'mid' : 'bad';
  return '<b class="wr ' + cls + '">' + wr + '%</b> <span class="faint">' + n + 'g</span>';
}

/* ---- the tables ----------------------------------------------------------- */
// Rows shown for every role, then the rows that only mean something for one.
// A support's damage is not a support's job, so it is not in their table.
const ROLE_ROWS = {
  Tank: [['mit', 'mitigation / map'], ['dmg', 'damage / map'], ['deaths', 'deaths / map']],
  Damage: [['dmg', 'damage / map'], ['elims', 'elims / map'], ['deaths', 'deaths / map']],
  Support: [['heal', 'healing / map'], ['dmg', 'damage / map'], ['deaths', 'deaths / map']],
  Unassigned: [['dmg', 'damage / map'], ['heal', 'healing / map'], ['mit', 'mitigation / map']]
};

// A player's stats and Eff are season-wide: FACEIT reports them per game, but
// the export rolls them up per player per division with no role split. For their
// DOMINANT role that is a fair label. In a SECOND table it is not — Warglabidoo's
// 7 Tank maps carry the averages of his 60 Damage ones, and his Eff peer group is
// still Damage. The numbers are shown anyway (they are the only ones there are)
// but every one of them is marked, so nobody reads them as Tank-only.
function isSecondary(f, role) { return ((f.idx.tables || [])[0] || UNASSIGNED_LABEL) !== role; }
const UNASSIGNED_LABEL = 'Unassigned';
const ALLROLES = ' <span class="faint allroles" title="season-wide across every role this player played — the data carries no per-role split">all roles</span>';

function tableFor(role, facts) {
  const wrap = el('<div class="rt"></div>');
  wrap.appendChild(el('<h2>' + esc(role) + ' <span class="note">' +
    facts.length + (facts.length === 1 ? ' player' : ' players') + '</span></h2>'));
  const flex = facts.filter(function (f) { return isSecondary(f, role); });
  if (flex.length) {
    wrap.appendChild(el('<p class="note warn">' +
      flex.map(function (f) { return esc(f.nick); }).join(', ') +
      (flex.length === 1 ? ' plays ' : ' play ') + 'this role as a second role. ' +
      'Their stats and Eff below are season-wide, not ' + esc(role) + '-only — the ' +
      'data has no per-role split, and their Eff peer group is still their main role.</p>'));
  }

  const rows = [];
  const push = function (label, cell, cls) { rows.push({ label: label, cell: cell, cls: cls || '' }); };

  push('team', function (f) {
    if (!f.found) return '<span class="faint" title="not in this build\'s divisions">not in this build</span>';
    return f.cur ? esc(f.cur.team) : '<span class="faint">no current team</span>';
  });
  push('division', function (f) {
    const i = f.idx;
    return '<span class="note">' + esc([i.region, i.tier].filter(Boolean).join(' ') || '—') + '</span>';
  });
  push('last played', function (f) { return '<span class="note">' + esc(dshort(f.idx.last)) + '</span>'; });
  push('roles', function (f) {
    const r = f.idx.roles || {};
    const parts = Object.keys(r).map(function (k) {
      const own = k === role ? ' class="own"' : '';
      return '<span' + own + '>' + esc(k) + ' ' + r[k] + '</span>';
    });
    return '<span class="note">' + (parts.join(' · ') || '—') + '</span>';
  });
  push('maps played', function (f) { return '<b>' + f.games + '</b>'; });
  push('map win rate', function (f) {
    return f.games ? rateCell(f.wr, f.games, 1, 'A win rate') + ' <span class="faint">' +
      f.wins + '-' + (f.games - f.wins) + '</span>' : '—';
  });
  push('elo', function (f) { return f.d0.elo == null ? '—' : '<b>' + f.d0.elo + '</b>'; });
  push('Eff', function (f) {
    const e = f.eff;
    if (!e || e.eff == null) {
      return '<span class="faint" title="needs ' + LB_MIN_GAMES + '+ maps and ' +
        EFF_GROUP_MIN + '+ same-role peers">—</span>';
    }
    const v = (e.eff > 0 ? '+' : '') + e.eff.toFixed(2);
    return '<b class="' + (e.eff > 0 ? 'good' : 'bad') + '">' + v + '</b>' +
      '<span class="faint"> vs ' + esc(e.group || '') + ', ' + e.groupN + ' peers in ' +
      esc(f.d0.division || '—') + '</span>' + (isSecondary(f, role) ? ALLROLES : '');
  }, 'sep');
  push('K/D', function (f) {
    if (!f.stats || f.stats.kd == null) return '—';
    return '<b>' + f.stats.kd + '</b>' + (isSecondary(f, role) ? ALLROLES : '');
  });
  (ROLE_ROWS[role] || []).forEach(function (pair) {
    push(pair[1], function (f) {
      if (!f.stats) return '—';
      return nf(f.stats[pair[0]]) + (isSecondary(f, role) ? ALLROLES : '');
    });
  });

  // Modes, then maps: the union of what the pooled players actually played,
  // busiest first. A mode nobody in this table played is not a row.
  const modeTot = {};
  facts.forEach(function (f) {
    f.S.modes.forEach(function (m) { modeTot[m.mode] = (modeTot[m.mode] || 0) + m.games; });
  });
  const modes = Object.keys(modeTot).sort(function (a, b) { return modeTot[b] - modeTot[a]; });
  modes.forEach(function (mode, i) {
    push(mode, function (f) {
      const m = f.S.modes.find(function (x) { return x.mode === mode; });
      if (!m) return '<span class="faint">—</span>';
      const team = m.teamWr == null ? '' : ' · their team ' + m.teamWr + '% over ' + m.teamGames;
      return '<span title="' + esc(mode + ': ' + m.wins + '-' + (m.games - m.wins) + team) + '">' +
        rateCell(m.wr, m.games, PLAYER_MODE_MIN, 'A mode win rate') + '</span>';
    }, i === 0 ? 'sep' : '');
  });

  const table = el('<table></table>');
  const head = el('<tr><th class="rowlab"></th></tr>');
  facts.forEach(function (f) {
    const th = el('<th></th>');
    th.appendChild(el('<div class="pn">' + esc(f.nick) + '</div>'));
    if (f.idx.game && f.idx.game !== f.nick) {
      th.appendChild(el('<div class="gn">“' + esc(f.idx.game) + '”</div>'));
    }
    if (isSecondary(f, role)) {
      const here = (f.idx.roles || {})[role] || 0;
      th.appendChild(el('<div class="fx">second role · ' + here + ' of ' +
        f.idx.maps + ' maps</div>'));
    }
    const x = el('<button class="x" title="remove from pool">×</button>');
    x.addEventListener('click', function () { removeFromPool(f.nick); });
    th.appendChild(x);
    head.appendChild(th);
  });
  table.appendChild(head);
  rows.forEach(function (r) {
    const tr = el('<tr class="' + r.cls + '"></tr>');
    tr.appendChild(el('<td class="rowlab">' + esc(r.label) + '</td>'));
    facts.forEach(function (f) { tr.appendChild(el('<td>' + r.cell(f) + '</td>')); });
    table.appendChild(tr);
  });
  wrap.appendChild(table);
  wrap.appendChild(mapsDetail(facts));
  wrap.appendChild(heroesDetail(facts));
  return wrap;
}

function mapsDetail(facts) {
  const d = el('<details class="sub"><summary>Per-map records <span class="note">needs ' +
    PLAYER_MAP_MIN + '+ games on the map</span></summary></details>');
  const tot = {};
  facts.forEach(function (f) {
    f.S.maps.forEach(function (m) { tot[m.map] = (tot[m.map] || 0) + m.games; });
  });
  const names = Object.keys(tot).sort(function (a, b) { return tot[b] - tot[a]; });
  if (!names.length) { d.appendChild(el('<p class="note">No maps recorded.</p>')); return d; }
  const table = el('<table></table>');
  const head = el('<tr><th class="rowlab"></th></tr>');
  facts.forEach(function (f) { head.appendChild(el('<th>' + esc(f.nick) + '</th>')); });
  table.appendChild(head);
  names.forEach(function (map) {
    const tr = el('<tr></tr>');
    tr.appendChild(el('<td class="rowlab">' + esc(map) + '</td>'));
    facts.forEach(function (f) {
      const m = f.S.maps.find(function (x) { return x.map === map; });
      tr.appendChild(el('<td>' + (m ? rateCell(m.wr, m.games, PLAYER_MAP_MIN, 'A map win rate')
        : '<span class="faint">—</span>') + '</td>'));
    });
    table.appendChild(tr);
  });
  d.appendChild(table);
  return d;
}

// Hero pools come from replay captures, which reach a small minority of players.
// The section says so rather than letting an absent pool read as a narrow one.
function heroesDetail(facts) {
  const any = facts.some(function (f) { return f.S.heroes && f.S.heroes.length; });
  const d = el('<details class="sub"><summary>Hero pool <span class="note">' +
    'from replay captures only — thin, and absence is not evidence</span></summary></details>');
  if (!any) {
    d.appendChild(el('<p class="note">No captured heroes for anyone in this table.</p>'));
    return d;
  }
  const table = el('<table></table>');
  const head = el('<tr></tr>');
  facts.forEach(function (f) { head.appendChild(el('<th>' + esc(f.nick) + '</th>')); });
  table.appendChild(head);
  const tr = el('<tr></tr>');
  facts.forEach(function (f) {
    const hs = (f.S.heroes || []).slice(0, 6);
    tr.appendChild(el('<td>' + (hs.length
      ? hs.map(function (h) {
        return '<div class="hero">' + esc(h.hero) + ' <span class="faint">' +
          (h.share == null ? '' : Math.round(h.share * 100) + '%') + '</span></div>';
      }).join('')
      : '<span class="faint">no captures</span>') + '</td>'));
  });
  table.appendChild(tr);
  d.appendChild(table);
  return d;
}

/* ---- pool + search -------------------------------------------------------- */
function addToPool(nick) {
  if (POOL.indexOf(nick) >= 0) return;
  POOL.push(nick); savePool(); render();
}
function removeFromPool(nick) {
  POOL = POOL.filter(function (n) { return n !== nick; });
  savePool(); render();
}

function searchMatches(q) {
  q = (q || '').trim().toLowerCase();
  if (!q) return [];
  return IDX.filter(function (e) {
    return String(e.nick || '').toLowerCase().indexOf(q) >= 0 ||
      String(e.game || '').toLowerCase().indexOf(q) >= 0;
  }).slice(0, 40);
}

function renderResults(q) {
  const box = document.getElementById('results');
  box.innerHTML = '';
  const query = (q || '').trim();
  if (!query) return;
  const hits = searchMatches(query);
  if (!hits.length) {
    // The expected outcome for a good share of any real shortlist: a third of
    // one 24-name sheet had no league player under either name. Say so.
    box.appendChild(el('<p class="note">No league player matches “' + esc(query) +
      '” under either their FACEIT nickname or their in-game name.</p>'));
    return;
  }
  hits.forEach(function (e) {
    const pooled = POOL.indexOf(e.nick) >= 0;
    const r = el('<button class="hit' + (pooled ? ' pooled' : '') + '"></button>');
    r.innerHTML = '<span class="n">' + esc(e.nick) + '</span>' +
      (e.game && e.game !== e.nick ? '<span class="g">“' + esc(e.game) + '”</span>' : '') +
      '<span class="meta">' + esc([e.role, e.region, e.tier, e.team].filter(Boolean).join(' · ')) +
      ' · ' + e.maps + ' maps</span>' +
      (pooled ? '<span class="tag">in pool</span>' : '');
    if (!pooled) r.addEventListener('click', function () { addToPool(e.nick); });
    box.appendChild(r);
  });
}

function renderPool() {
  const box = document.getElementById('pool');
  box.innerHTML = '';
  if (!POOL.length) return;
  POOL.forEach(function (nick) {
    const c = el('<span class="chip">' + esc(nick) + '</span>');
    const x = el('<button class="x" title="remove">×</button>');
    x.addEventListener('click', function () { removeFromPool(nick); });
    c.appendChild(x);
    box.appendChild(c);
  });
  const clear = el('<button class="clear">clear pool</button>');
  clear.addEventListener('click', function () {
    if (confirm('Remove all ' + POOL.length + ' players from the pool?')) {
      POOL = []; savePool(); render();
    }
  });
  box.appendChild(clear);
}

function render() {
  renderPool();
  renderResults(document.getElementById('q').value);
  const main = document.getElementById('tables');
  main.innerHTML = '';
  if (!POOL.length) {
    main.appendChild(el('<p class="note empty">Search for a player above to start a pool. ' +
      'Both the FACEIT nickname and the in-game name match.</p>'));
    return;
  }
  const facts = {};
  POOL.forEach(function (n) { facts[n] = factsFor(n); });
  TABLE_ORDER.forEach(function (role) {
    const inRole = POOL.filter(function (n) {
      const t = (BY_NICK[n] || {}).tables || ['Unassigned'];
      return t.indexOf(role) >= 0;
    }).map(function (n) { return facts[n]; });
    if (inRole.length) main.appendChild(tableFor(role, inRole));
  });
  // A pooled player the payload does not know at all still gets said out loud
  // rather than silently vanishing from every table.
  const unknown = POOL.filter(function (n) { return !BY_NICK[n]; });
  if (unknown.length) {
    main.appendChild(el('<p class="note">Not in this build’s divisions: ' +
      unknown.map(esc).join(', ') + '. Rebuild without --season/--region filters to include them.</p>'));
  }
}

function boot() {
  const q = document.getElementById('q');
  q.addEventListener('input', function () { renderResults(q.value); });
  if (!STORAGE_OK) {
    document.getElementById('pool').appendChild(
      el('<span class="note">localStorage unavailable — this pool lasts for this page view only.</span>'));
  }
  document.getElementById('built').textContent =
    IDX.length + ' players indexed · built ' + dshort(DATA.built_at);
  render();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
else boot();
