// tools/replay_bot/score.js
// What the bot said a map was, against what the map actually was.
//
//   node tools/replay_bot/score.js out/replay-bot-2026-09-09.json
//   node tools/replay_bot/score.js out/*.json --verbose
//
// EVERY BUG THIS PROJECT HAS PAID FOR WAS INVISIBLE IN THE OUTPUT. A batch of
// seek presses that landed one step instead of nine produced six plausible
// samples. A closed events panel turned a three-round map into one continuous
// segment, confidently. A matcher scoring hero templates against a black
// loading screen returned 0.29 to 0.63 and no sign anything was wrong. In every
// case the contribution file looked exactly like a good one.
//
// So "the cycle ran" has never been the question. The question is whether the
// heroes it read are the heroes that were played, and until now nothing could
// answer it - a public replay comes with no answer key.
//
// IT TURNS OUT IT DOES. owreplays.tv serves an event stream per code:
// PLAYER_JOINED gives the opening five a side, PLAYER_PICKED_HERO gives every
// swap with its timestamp, and ROUND_START/ROUND_END give the round structure.
// That is an independent answer key for both things the bot claims - the
// composition at a moment, and how many rounds the map had - written by
// somebody else's parser from the replay file itself.
//
// The two vocabularies meet on hero names: the bot emits Blizzard GUIDs and
// names them from refs.json, the site numbers its own. Normalised, they join
// 53 against 53 with nothing left over, so no alias table is needed and none
// should be added without checking that count again.
//
// THE ANSWER KEY IS OFTEN INCOMPLETE, AND SCORING AGAINST IT ANYWAY IS WORSE
// THAN NOT SCORING. On many replays the site's parse never sees all ten
// players: measured across four maps, only one had five heroes a side at every
// sampled moment, and another had as few as two. An observation graded against
// a three-player key can never be "exact" no matter how right the bot was, so
// those are counted and set aside rather than folded into a percentage. The
// first cut of this reported 52.3% exact and that number meant nothing.
//
// WHAT A GOOD SCORE IS NOT. This grades a read against a parse, and the parse
// can be wrong too - it is another program reading the same replay. Treat a
// disagreement as somewhere to go and look at the retained frame, which is
// still on disk, rather than as a verdict. contact_sheet.js renders the ten
// crops of any of them.
//
// AND CHECK THE MODE COLUMN BEFORE BELIEVING ANY OF IT. A FACEIT game is
// competitive role queue. Six of the first eight maps this bot ever captured
// were quick play, which nobody noticed until this tool printed the mode next
// to the score - different round structure, sparser events, and a thinner parse
// on the site. A percentage measured on the wrong kind of game is not a
// measurement of anything.

const fs = require('fs');
const path = require('path');

(function (global) {
  'use strict';

  // --------------------------------------------------------------- pure ----

  // Hero names, stripped to something two sources can agree on: accents folded,
  // punctuation and spaces dropped, lowercased. "D.Va" and "DVa" and "d va" are
  // one hero; "Soldier: 76" is soldier76.
  function normaliseName(s) {
    return String(s)
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '');
  }

  // Who was on which hero, when.
  //
  // A slot's hero is whatever it JOINED as until a pick changes it, and from
  // that pick's own second onward. Sorting by time first is what makes the
  // result independent of the order the site happened to store events in.
  function heroTimeline(events) {
    const slots = new Map();          // slot -> { team, changes: [{at, hero}] }

    const ordered = events.slice().sort((a, b) => (a.time || 0) - (b.time || 0));
    for (const e of ordered) {
      if (e.hero === null || e.hero === undefined) continue;
      if (e.type !== 'PLAYER_JOINED' && e.type !== 'PLAYER_PICKED_HERO') continue;
      if (e.slot === null || e.slot === undefined || e.slot === '') continue;

      const key = String(e.slot);
      if (!slots.has(key)) slots.set(key, { team: String(e.team), changes: [] });
      slots.get(key).changes.push({ at: e.time || 0, hero: e.hero });
    }
    return slots;
  }

  // The heroes a side had on at `t` seconds - one per slot, so a duplicated
  // hero appears twice.
  function heroesAt(timeline, team, t) {
    const out = [];
    for (const slot of timeline.values()) {
      if (slot.team !== String(team)) continue;
      let hero = null;
      for (const c of slot.changes) {
        if (c.at <= t) hero = c.hero; else break;
      }
      if (hero !== null) out.push(hero);
    }
    return out;
  }

  // Read against played, as multisets: the bot reads five portraits left to
  // right and the site numbers its own slots, so nothing guarantees the two
  // orders agree - but two Anas must still need two Anas.
  function compare(read, played) {
    const pool = played.slice();
    const extra = [];
    let matched = 0;
    for (const r of read) {
      const i = pool.indexOf(r);
      if (i === -1) extra.push(r); else { pool.splice(i, 1); matched++; }
    }
    return { matched, missing: pool, extra };
  }

  // The map's rounds, from the markers the site's parser emitted. A round left
  // open at the end of the stream is still a round - the replay just stops.
  function rounds(events) {
    const byNo = new Map();
    for (const e of events) {
      if (e.type !== 'ROUND_START' && e.type !== 'ROUND_END') continue;
      const no = e.round === null || e.round === undefined ? byNo.size + 1 : e.round;
      if (!byNo.has(no)) byNo.set(no, { no, start: null, end: null });
      if (e.type === 'ROUND_START') byNo.get(no).start = e.time;
      else byNo.get(no).end = e.time;
    }
    return [...byNo.values()].sort((a, b) => a.no - b.no);
  }

  const Mod = { normaliseName, heroTimeline, heroesAt, compare, rounds };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayScore = Mod;
})(typeof self !== 'undefined' ? self : this);

// ----------------------------------------------------------------- main ----

if (require.main === module) {
  const S = module.exports;
  const API = 'https://owreplays.tv/api/v2/';

  const files = process.argv.slice(2).filter((a) => !a.startsWith('--'));
  const verbose = process.argv.includes('--verbose');

  const get = async (url) => {
    const r = await fetch(url, { headers: { 'user-agent': 'Mozilla/5.0' } });
    if (!r.ok) throw new Error(url + ' -> HTTP ' + r.status);
    return r.json();
  };

  const pad = (s, n) => String(s).padEnd(n);
  const pct = (a, b) => (b ? (100 * a / b).toFixed(1) + '%' : '-');

  (async () => {
    if (!files.length) {
      console.log('usage: node tools/replay_bot/score.js <contribution.json> [--verbose]');
      return;
    }

    // GUID -> name, from the same reference library the matcher reads.
    const refs = require(path.join(__dirname, '../../docs/capture/refs.json')).refs;
    const nameOfGuid = new Map(refs.map((r) => [r.g, S.normaliseName(r.n)]));

    // The site's hero numbering -> the same normalised names.
    const heroes = await get(API + 'heroes');
    const nameOfId = new Map(heroes.map((h) => [h.ID, S.normaliseName(h.hero)]));

    let obsTotal = 0, cellsTotal = 0, cellsRight = 0, exactReads = 0, partialKeys = 0;
    const confusions = new Map();

    const allMaps = await get(API + 'maps');
    const mapById = new Map(allMaps.map((m) => [m.ID, m]));

    for (const file of files) {
      const doc = JSON.parse(fs.readFileSync(file, 'utf8'));
      console.log(`\n=== ${file} - ${doc.maps.length} maps, ${doc.tool_version} ===\n`);
      console.log(pad('CODE', 8) + pad('MAP', 16) + pad('TYPE', 11) + pad('MODE', 20) +
        pad('CELLS', 8) + pad('EXACT', 8) + pad('ROUNDS', 9) + 'NOTE');

      for (const map of doc.maps) {
        const code = map.demo_code;

        // What kind of game was this? A score on a quick play map says nothing
        // about a FACEIT one, so it goes in the table rather than a footnote.
        let mapName = '?', mapType = '?', modeName = '?';
        try {
          const rec = await get(API + 'replay/' + code);
          const r = rec.replay || rec;
          const m = mapById.get(r.Map);
          if (m) { mapName = m.map; mapType = m.mode || '?'; }
          modeName = (r.Mode === 2 ? 'competitive' : r.Mode === 1 ? 'QUICK PLAY' : 'mode ' + r.Mode) +
            (r.GameType === 1 ? ' RQ' : r.GameType === 2 ? ' OQ' : '');
        } catch (e) { /* the score still stands without it */ }

        let events;
        try {
          const res = await get(API + 'replay/' + code + '/events');
          events = res.events || [];
        } catch (e) {
          console.log(pad(code, 8) + pad(mapName, 16) + pad(mapType, 11) + pad(modeName, 20) +
            pad('-', 8) + pad('-', 8) + pad('-', 9) + 'no answer key');
          continue;
        }
        if (!events.length) {
          console.log(pad(code, 8) + pad(mapName, 16) + pad(mapType, 11) + pad(modeName, 20) +
            pad('-', 8) + pad('-', 8) + pad('-', 9) + 'the site has no events for this code');
          continue;
        }

        const timeline = S.heroTimeline(events);
        const truthRounds = S.rounds(events);

        let cells = 0, right = 0, exact = 0, scored = 0, partial = 0;
        for (const obs of map.observations) {
          const t = obs.ts / 1000;
          const team = obs.side === 'a' ? '1' : '2';
          const read = obs.heroes.map((g) => nameOfGuid.get(g) || ('?' + g));
          const played = S.heroesAt(timeline, team, t).map((id) => nameOfId.get(id) || ('#' + id));
          // A key that does not have all five is not a key. Counted, not graded.
          if (played.length !== 5) { partial++; partialKeys++; continue; }

          const r = S.compare(read, played);
          scored++;
          cells += played.length;
          right += r.matched;
          if (r.matched === played.length && read.length === played.length) exact++;
          obsTotal++;

          r.extra.forEach((e, i) => {
            const was = r.missing[i];
            if (!was) return;
            const key = was + ' read as ' + e;
            confusions.set(key, (confusions.get(key) || 0) + 1);
          });

          if (verbose && r.matched !== played.length) {
            console.log(`    ${code} ${obs.side} t=${Math.round(t)}s  ` +
              `played ${played.sort().join(' ')}\n` +
              `${' '.repeat(20)}read   ${read.sort().join(' ')}`);
          }
        }

        const botRounds = Math.max(0, ...map.observations.map((o) => o.round_no || 0));
        const roundsCell = botRounds + ' vs ' + truthRounds.length;
        const notes = [];
        if (botRounds !== truthRounds.length) notes.push('ROUNDS DISAGREE');
        if (partial) notes.push(partial + ' of ' + map.observations.length + ' had a partial key');

        cellsTotal += cells; cellsRight += right; exactReads += exact;
        console.log(pad(code, 8) + pad(mapName, 16) + pad(mapType, 11) + pad(modeName, 20) +
          pad(scored ? pct(right, cells) : '-', 8) + pad(scored ? exact + '/' + scored : '-', 8) +
          pad(roundsCell, 9) + notes.join('; '));
      }
    }

    console.log('\n' + '-'.repeat(60));
    console.log(`${obsTotal} observations scored against a complete five-a-side key` +
      (partialKeys ? `, ${partialKeys} set aside because the key was incomplete` : ''));
    console.log(`heroes read correctly: ${cellsRight}/${cellsTotal}  (${pct(cellsRight, cellsTotal)})`);
    console.log(`compositions read exactly right: ${exactReads}/${obsTotal}  (${pct(exactReads, obsTotal)})`);

    if (confusions.size) {
      console.log('\nmost confused, played -> read:');
      [...confusions.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12)
        .forEach(([k, n]) => console.log('  ' + pad(n, 4) + k));
      console.log('\nthe frames are still on disk - contact_sheet.js renders the ten crops of one.');
    }
  })().catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; });
}
