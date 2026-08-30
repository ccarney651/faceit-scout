/* ---------- trialist comparison: the local tool's whole UI ----------
   Runs on top of pure.js, which is inlined ahead of it unchanged. Every rate,
   record and z-score on this page comes from there — playerSeason(),
   efficiencyRatings(), playerRate() — so a number here and the same number on
   owdb.io cannot disagree.

   Players are ROWS, metrics are columns, one table per role: comparing down a
   column beats comparing across a horizontal scrollbar. Click any header to
   sort; click a player to expand their modes, maps and hero pool.

   The window/document touches are guarded so the file loads under plain node,
   which is what lets tests/test_trials.py execute teamTotals() and sortRows()
   for real instead of smoke-testing them through a screenshot.

   Not part of the dashboard: faceit_sync/_dashboard.py::_PARTS names its parts
   explicitly, and this file is not one of them. */

const HAS_WINDOW = typeof window !== 'undefined';
const DATA = (HAS_WINDOW && window.__OWDB_DATA__) || {};
const IDX = (HAS_WINDOW && window.__TRIALS_INDEX__) || [];
const DIVS = DATA.divisions || {};
const COMPS = DATA.owdb_comps || {};
const PERGAME = DATA.owdb_pergame_players || {};

const POOL_KEY = 'owdb-trials-pool';
const TABLE_ORDER = ['Tank', 'Damage', 'Support', 'Unassigned'];
const UNASSIGNED_LABEL = 'Unassigned';
const BY_NICK = {};
IDX.forEach(function (e) { BY_NICK[e.nick] = e; });

// STORAGE_OK must be initialised BEFORE loadPool() runs: loadPool's catch branch
// assigns to it, and a `let` read before initialisation is a TDZ error, not a
// warning. That branch only fires when localStorage is blocked — i.e. the
// fallback written to keep the page working would itself have killed it.
let STORAGE_OK = true;
let POOL = loadPool();
// Sorted by the sample-weighted Eff, not the raw one: the raw number's top end
// is mostly small-sample noise (see adjustedEff).
let SORT = { key: 'adj', dir: 'desc' };

// How hard a small sample is pulled toward the group mean. Measured across 1123
// players by fitting observed variance = skill + noise/n: skill 0.062, noise
// 3.64, which implies a "correct" k of 59. That is strong enough to flatten
// almost everyone, and 15 already does the whole job — styxywhixy's +0.71 over 8
// maps drops from 1st to 4th at 15 and stays 4th at 30 and 59. Beyond 15 the
// ordering stops changing and only the numbers compress, so 15 it is.
const EFF_SHRINK = 15;

/* ---- pure helpers (executed by the tests) --------------------------------- */

// One team's whole season, summed from teamRecords(). Integer games and wins, so
// the team rate a player is judged against is never re-derived from a rounded
// percentage. An unknown team is {0,0,null} — never a 0% win rate, which would
// read as "lost everything" rather than "no record".
function teamTotals(records, cid, team) {
  const rec = ((records || {})[cid + '|' + team] || {}).map || {};
  let games = 0, wins = 0;
  Object.keys(rec).forEach(function (m) {
    games += rec[m].games || 0;
    wins += rec[m].wins || 0;
  });
  return { games: games, wins: wins, wr: games ? Math.round(100 * wins / games) : null };
}

// Eff pulled toward its group mean in proportion to sample size — the standard
// regression-to-the-mean correction for a rate measured over few observations.
//
// Eff is a mean of z-scores of per-MAP averages, so a short season is not merely
// less reliable, it is WIDER: measured over 1123 players, SD of Eff is 0.679 at
// 5-14 maps against 0.356 at 50+, and 12.6% of low-sample players clear |Eff|>1
// against 1.0% of the high-sample ones. Sorting on the raw number therefore
// fills the top of the list with whoever played least.
//
// It only ever scales toward zero: a sign never flips, and an Eff that was
// absent (below its own floor) stays absent rather than becoming a number.
function adjustedEff(eff, n) {
  if (eff == null) return null;
  const g = n || 0;
  return eff * (g / (g + EFF_SHRINK));
}

// Sort rows by one column. A missing value sorts LAST in both directions: a
// candidate whose Eff is under its sample floor has not earned the top of the
// list, and ascending must not reward them either. Ties break by name so the
// order never wobbles between renders.
function sortRows(rows, key, dir) {
  return (rows || []).slice().sort(function (a, b) {
    const x = (a.sort || {})[key], y = (b.sort || {})[key];
    if (x == null && y == null) return String(a.nick).localeCompare(String(b.nick));
    if (x == null) return 1;
    if (y == null) return -1;
    if (x === y) return String(a.nick).localeCompare(String(b.nick));
    return dir === 'asc' ? (x < y ? -1 : 1) : (x > y ? -1 : 1);
  });
}

// A player's stats and Eff are season-wide: the export rolls them up per player
// per division with no role split. For their DOMINANT role that is a fair label.
// In a SECOND table it is not — Warglabidoo's 7 Tank maps carry the averages of
// his 60 Damage ones, and his Eff peer group is still Damage. The numbers show
// anyway (they are the only ones there are) but every one is marked.
function isSecondary(entry, role) {
  return (((entry || {}).tables || [])[0] || UNASSIGNED_LABEL) !== role;
}

/* ---- storage -------------------------------------------------------------- */
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

/* ---- DOM helpers ---------------------------------------------------------- */
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
function signed(n, dp) {
  if (n == null) return '—';
  const v = dp ? n.toFixed(dp) : String(Math.round(n));
  return (n > 0 ? '+' : '') + v;
}

/* ---- Eff cohorts -----------------------------------------------------------
   Copied from app.js (roleOf / ROLE_SEATS / seatOfPlayer / effGroupOf /
   playerCaptures) rather than approximated, so the peer group here is the same
   peer group the site uses. Only the cohort assignment is duplicated; the rating
   itself is pure.js's efficiencyRatings(). If app.js's version changes, this one
   has to follow — the two are a knowing fork, kept small on purpose. */
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
// An Eff is a comparison, so it cannot be computed for one player alone — and
// certainly not against the trialist pool, which is not a peer group. The cohort
// is the whole division, exactly as the Players tab builds it.
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
let TEAMREC = null;
function teamRecordsOnce() {
  if (TEAMREC === null) TEAMREC = teamRecords(DIVS);
  return TEAMREC;
}

// The team's record over the spells this player actually had. Their own win rate
// is 82% explained by which team they were on (measured across 1016 players), so
// this column is what makes the win-rate column readable at all.
function teamContext(S) {
  const recs = teamRecordsOnce();
  const seen = {};
  let games = 0, wins = 0;
  (S.teams || []).forEach(function (sp) {
    const k = sp.cid + '|' + sp.team;
    if (seen[k]) return;
    seen[k] = 1;
    const t = teamTotals(recs, sp.cid, sp.team);
    games += t.games; wins += t.wins;
  });
  return { games: games, wins: wins, wr: games ? Math.round(100 * wins / games) : null };
}

const ROLE_STAT = {
  Tank: ['mit', 'mitigation / map'],
  Damage: ['dmg', 'damage / map'],
  Support: ['heal', 'healing / map'],
  Unassigned: ['dmg', 'damage / map']
};

function factsFor(nick, role) {
  const S = playerSeason(nick, DIVS, COMPS, PERGAME);
  const idx = BY_NICK[nick] || {};
  const cur = S.current;
  // The division they are in NOW, not the one with the most maps: a player who
  // moved up mid-season has a stale elo and a stale peer group in the old one.
  const d0 = (cur && S.divisions.find(function (d) { return d.cid === cur.cid; })) || S.divisions[0] || {};
  const games = S.maps.reduce(function (a, m) { return a + m.games; }, 0);
  const wins = S.maps.reduce(function (a, m) { return a + m.wins; }, 0);
  const team = teamContext(S);
  const eff = effFor(nick, d0.cid);
  const stats = d0.stats || null;
  const statKey = (ROLE_STAT[role] || ROLE_STAT.Unassigned)[0];
  const wr = games ? 100 * wins / games : null;
  const twr = team.games ? 100 * team.wins / team.games : null;
  return {
    nick: nick, idx: idx, S: S, cur: cur, d0: d0, found: S.found,
    games: games, wins: wins, team: team, eff: eff, stats: stats,
    secondary: isSecondary(idx, role),
    sort: {
      nick: null, maps: games,
      wr: wr == null ? null : Math.round(wr),
      teamWr: team.wr,
      delta: (wr == null || twr == null) ? null : Math.round(10 * (wr - twr)) / 10,
      elo: d0.elo == null ? null : d0.elo,
      eff: eff && eff.eff != null ? eff.eff : null,
      adj: eff && eff.eff != null ? adjustedEff(eff.eff, eff.n) : null,
      kd: stats && stats.kd != null ? stats.kd : null,
      stat: stats && stats[statKey] != null ? stats[statKey] : null
    }
  };
}

/* ---- the tables ----------------------------------------------------------- */
const ALLROLES = '<span class="faint allroles" title="season-wide across every role this player played — the data carries no per-role split">all roles</span>';

function wrClass(wr) { return wr == null ? '' : wr >= 60 ? 'good' : wr >= 45 ? 'mid' : 'bad'; }

function columnsFor(role) {
  const statPair = ROLE_STAT[role] || ROLE_STAT.Unassigned;
  return [
    {
      key: 'nick', label: 'player', align: 'l', cell: function (f) {
        return '<span class="pn">' + esc(f.nick) + '</span>' +
          (f.idx.game && f.idx.game !== f.nick
            ? '<span class="gn">“' + esc(f.idx.game) + '”</span>' : '') +
          (f.secondary
            ? '<span class="fx" title="' + esc(role) + ' is their second role — ' +
            ((f.idx.roles || {})[role] || 0) + ' of ' + f.idx.maps + ' maps">2nd role</span>' : '');
      }
    },
    {
      key: 'team', label: 'team', align: 'l', cell: function (f) {
        if (!f.found) return '<span class="faint">not in this build</span>';
        return f.cur ? esc(f.cur.team) : '<span class="faint">none</span>';
      }
    },
    {
      key: 'div', label: 'div', align: 'l', cell: function (f) {
        return '<span class="note">' +
          esc([f.idx.region, f.idx.tier].filter(Boolean).join(' ') || '—') + '</span>';
      }
    },
    { key: 'maps', label: 'maps', cell: function (f) { return f.games || '—'; } },
    {
      key: 'wr', label: 'win %', cell: function (f) {
        if (f.sort.wr == null) return '—';
        return '<b class="' + wrClass(f.sort.wr) + '">' + f.sort.wr + '%</b>' +
          '<span class="faint sub">' + f.wins + '-' + (f.games - f.wins) + '</span>';
      }
    },
    {
      key: 'teamWr', label: 'team %', cell: function (f) {
        return f.sort.teamWr == null
          ? '<span class="faint">—</span>'
          : '<span class="note">' + f.sort.teamWr + '%</span>' +
          '<span class="faint sub">' + f.team.games + 'g</span>';
      }
    },
    {
      key: 'delta', label: 'vs team',
      title: 'their win rate minus their team’s over the team’s whole season. ' +
        'Zero for a player who started every map — they ARE the team.',
      cell: function (f) {
        const d = f.sort.delta;
        if (d == null) return '—';
        if (Math.abs(d) < 0.05) {
          return '<span class="faint" title="started every map — nothing to diverge from">0</span>';
        }
        return '<b class="' + (d > 0 ? 'good' : 'bad') + '">' + signed(d, 1) + '</b>';
      }
    },
    { key: 'elo', label: 'elo', cell: function (f) { return f.sort.elo == null ? '—' : f.sort.elo; } },
    {
      key: 'eff', label: 'Eff',
      title: 'per-map stats z-scored against the same role in the same division. ' +
        'Only 22% explained by team quality, against 82% for win rate — the ' +
        'closest thing here to a team-independent number.',
      cell: function (f) {
        const e = f.eff;
        if (!e || e.eff == null) {
          return '<span class="faint" title="needs ' + LB_MIN_GAMES + '+ maps and ' +
            EFF_GROUP_MIN + '+ same-role peers">—</span>';
        }
        return '<b class="' + (e.eff > 0 ? 'good' : 'bad') + '">' + signed(e.eff, 2) + '</b>' +
          '<span class="faint sub" title="peer group">' + esc(e.group || '') + ' · ' + e.groupN + '</span>' +
          (f.secondary ? ALLROLES : '');
      }
    },
    {
      key: 'adj', label: 'Eff·n',
      title: 'Eff weighted by sample size — pulled toward the group mean by ' +
        'n/(n+' + EFF_SHRINK + '). A short season is not just less reliable, it is wider: ' +
        '12.6% of players under 15 maps post |Eff|>1 against 1.0% of those over 50. ' +
        'This is what the table sorts by.',
      cell: function (f) {
        if (f.sort.adj == null) return '<span class="faint">—</span>';
        const n = (f.eff && f.eff.n) || 0;
        return '<b class="' + (f.sort.adj > 0 ? 'good' : 'bad') + '">' + signed(f.sort.adj, 2) + '</b>' +
          '<span class="faint sub" title="stat sample behind it">' + n + 'g</span>';
      }
    },
    {
      key: 'kd', label: 'K/D', cell: function (f) {
        return (f.sort.kd == null ? '—' : f.sort.kd) + (f.secondary ? ALLROLES : '');
      }
    },
    {
      key: 'stat', label: statPair[1], cell: function (f) {
        return nf(f.sort.stat) + (f.secondary ? ALLROLES : '');
      }
    }
  ];
}

function tableFor(role, facts) {
  const wrap = el('<div class="rt"></div>');
  wrap.appendChild(el('<h2>' + esc(role) + ' <span class="note">' +
    facts.length + (facts.length === 1 ? ' player' : ' players') + '</span></h2>'));

  const flex = facts.filter(function (f) { return f.secondary; });
  if (flex.length) {
    wrap.appendChild(el('<p class="note warn">' +
      flex.map(function (f) { return esc(f.nick); }).join(', ') +
      (flex.length === 1 ? ' plays ' : ' play ') + 'this as a second role. Their stats and ' +
      'Eff are season-wide, not ' + esc(role) + '-only — the data has no per-role split, ' +
      'and their Eff peer group is still their main role.</p>'));
  }

  const cols = columnsFor(role);
  const table = el('<table class="cmp"></table>');
  const head = el('<tr></tr>');
  cols.forEach(function (c) {
    const on = SORT.key === c.key;
    const th = el('<th class="' + (c.align === 'l' ? 'l' : 'r') + (on ? ' on' : '') + '"' +
      (c.title ? ' title="' + esc(c.title) + '"' : '') + '>' + esc(c.label) +
      (on ? '<span class="ar">' + (SORT.dir === 'desc' ? '▾' : '▴') + '</span>' : '') + '</th>');
    th.addEventListener('click', function () {
      // Same column toggles direction; a new column starts descending, because
      // "most" is what you want first for every number in this table.
      if (SORT.key === c.key) SORT.dir = SORT.dir === 'desc' ? 'asc' : 'desc';
      else SORT = { key: c.key, dir: c.key === 'nick' ? 'asc' : 'desc' };
      render();
    });
    head.appendChild(th);
  });
  table.appendChild(head);

  sortRows(facts, SORT.key, SORT.dir).forEach(function (f) {
    const tr = el('<tr class="prow"></tr>');
    cols.forEach(function (c) {
      tr.appendChild(el('<td class="' + (c.align === 'l' ? 'l' : 'r') + '">' + c.cell(f) + '</td>'));
    });
    const drop = el('<tr class="detail"><td colspan="' + cols.length + '"></td></tr>');
    drop.style.display = 'none';
    let built = false;
    tr.addEventListener('click', function (ev) {
      if (ev.target.closest('button')) return;
      const open = drop.style.display === 'none';
      if (open && !built) { drop.firstElementChild.appendChild(detailFor(f)); built = true; }
      drop.style.display = open ? '' : 'none';
      tr.classList.toggle('open', open);
    });
    const rm = el('<button class="x" title="remove from pool">×</button>');
    rm.addEventListener('click', function () { removeFromPool(f.nick); });
    tr.firstElementChild.appendChild(rm);
    table.appendChild(tr);
    table.appendChild(drop);
  });
  wrap.appendChild(table);
  return wrap;
}

// Everything too long for a row: mode and map records, and the hero pool.
function detailFor(f) {
  const box = el('<div class="det"></div>');
  // Each heading and its table must be ONE grid child, or the grid scatters a
  // heading into one column and its own table into the next.
  const section = function (headHtml) {
    const s = el('<section></section>');
    s.appendChild(el(headHtml));
    box.appendChild(s);
    return s;
  };

  const modes = f.S.modes || [];
  const modeBox = section('<h3>By mode <span class="note">needs ' + PLAYER_MODE_MIN +
    '+ games · team’s rate beside</span></h3>');
  if (!modes.length) modeBox.appendChild(el('<p class="note">No games recorded.</p>'));
  else {
    const t = el('<table class="mini"></table>');
    modes.forEach(function (m) {
      t.appendChild(el('<tr><td class="l">' + esc(m.mode) + '</td>' +
        '<td class="r">' + (m.wr == null
          ? '<span class="faint" title="needs ' + PLAYER_MODE_MIN + '+ games; ' + m.games + ' so far">—</span>'
          : '<b class="' + wrClass(m.wr) + '">' + m.wr + '%</b>') +
        '<span class="faint sub">' + m.games + 'g</span></td>' +
        '<td class="r note">' + (m.teamWr == null ? '—' : 'team ' + m.teamWr + '%') + '</td></tr>'));
    });
    modeBox.appendChild(t);
  }

  const maps = f.S.maps || [];
  const mapBox = section('<h3>By map <span class="note">needs ' + PLAYER_MAP_MIN + '+ games</span></h3>');
  if (!maps.length) mapBox.appendChild(el('<p class="note">No maps recorded.</p>'));
  else {
    const t = el('<table class="mini"></table>');
    maps.forEach(function (m) {
      t.appendChild(el('<tr><td class="l">' + esc(m.map) + '</td>' +
        '<td class="r">' + (m.wr == null
          ? '<span class="faint" title="needs ' + PLAYER_MAP_MIN + '+ games; ' + m.games + ' so far">—</span>'
          : '<b class="' + wrClass(m.wr) + '">' + m.wr + '%</b>') +
        '<span class="faint sub">' + m.games + 'g</span></td>' +
        '<td class="r note">' + (m.teamWr == null ? '—' : 'team ' + m.teamWr + '%') + '</td></tr>'));
    });
    mapBox.appendChild(t);
  }

  // Hero pools come from replay captures, which reach a small minority of
  // players. Say so, so an absent pool never reads as a narrow one.
  const hs = f.S.heroes || [];
  const heroBox = section('<h3>Hero pool <span class="note">replay captures only — ' +
    'thin, and absence is not evidence</span></h3>');
  heroBox.appendChild(el(hs.length
    ? '<p>' + hs.slice(0, 8).map(function (h) {
      return '<span class="hero">' + esc(h.hero) +
        (h.share == null ? '' : ' <span class="faint">' + Math.round(h.share * 100) + '%</span>') +
        '</span>';
    }).join('') + '</p>'
    : '<p class="note">No captured heroes for this player.</p>'));

  if (f.S.teams && f.S.teams.length > 1) {
    const spellBox = section('<h3>Teams this season</h3>');
    spellBox.appendChild(el('<p class="note">' + f.S.teams.map(function (sp) {
      return esc(sp.team) + ' (' + sp.games + 'g, ' + esc(dshort(sp.firstSeen)) +
        ' → ' + esc(dshort(sp.lastSeen)) + ')';
    }).join(' · ') + '</p>'));
  }
  return box;
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
    // The expected outcome for a good share of any real shortlist: a third of one
    // 24-name sheet had no league player under either name. Say so.
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
  TABLE_ORDER.forEach(function (role) {
    const inRole = POOL.filter(function (n) {
      const t = (BY_NICK[n] || {}).tables || [UNASSIGNED_LABEL];
      return t.indexOf(role) >= 0;
    }).map(function (n) { return factsFor(n, role); });
    if (inRole.length) main.appendChild(tableFor(role, inRole));
  });
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

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
}
