// tools/replay_bot/reprocess_attribution.js
// Re-run player attribution's name OCR against already-captured maps, now
// that docs/capture/engine/frames.js's findNameRow no longer breaks on a
// bright/team-colour-tinted plate (specs/2026-09-15-nameplate-fill-heuristic-
// handoff.md). Targets maps whose review artifact already shows an abstained
// slot (attribution.<side>.ids contains null) where a roster exists to
// attribute against - there is nothing to fix on a map with no roster, and a
// map a human has already corrected is left untouched.
//
// This works from the SAVED CROP PNGs alone, not a live client: review_out.js's
// writeStrip() crops exactly [box.x, box.x+box.w] x [box.y-PAD_Y,
// box.y+box.h+PAD_Y] out of the original frame, so rebasing the crop's own
// image as { x:0, y:PAD_Y, w:img.width, h:img.height-2*PAD_Y } reproduces
// nameplate.js's nameRow()/nameCrop() exactly as they'd run against the live
// frame - the same equivalence nameplate_fill_sweep.js already relies on.
//
// Role-constrained assignment needs a per-slot guid to look up roles by
// (assign.js's tie-breaker, not its primary evidence - name reads still
// decide most slots on their own). Production resolves this from the map's
// very first raw sample; this instead uses round 1's ALREADY-RESOLVED guid
// per slot, which is the same underlying evidence after voting rather than
// before it - a reasonable stand-in, not a byte-identical replay.
//
// Usage: node tools/replay_bot/reprocess_attribution.js [session-dir] [--dry]
//   default session: out/replay-bot-2026-09-15-full
//   --dry: compute and report, do not write the review artifact back

'use strict';

const fs = require('fs');
const path = require('path');
const { loadImage } = require('@napi-rs/canvas');
const Tesseract = require('tesseract.js');

const REPO = path.join(__dirname, '..', '..');
const Nameplate = require('./nameplate.js');
const Resolve = require('./resolve.js');
const Attribute = require('./attribute.js');
const Assign = require(path.join(REPO, 'docs/capture/engine/assign.js'));
const Names = require(path.join(REPO, 'docs/capture/engine/names.js'));

const args = process.argv.slice(2).filter((a) => a !== '--dry');
const DRY = process.argv.includes('--dry');
const SESSION = args[0] || path.join(__dirname, 'out', 'replay-bot-2026-09-15-full');
const REVIEW_PATH = SESSION + '.review.json';
const SIDES = ['a', 'b'];
const PAD_Y = 12;

const FEED = JSON.parse(fs.readFileSync(path.join(REPO, 'docs', 'capture', 'data.json'), 'utf8'));
const HERO_ROLES = FEED.hero_roles || {};

function rebaseBox(img) {
  return { x: 0, y: PAD_Y, w: img.width, h: img.height - 2 * PAD_Y };
}

function firstFramePath(map, side) {
  var frames = map.frames || {};
  var keys = Object.keys(frames).map(Number).sort((a, b) => a - b);
  for (var i = 0; i < keys.length; i++) {
    var f = frames[String(keys[i])];
    if (f && f[side]) return f[side];
  }
  return null;
}

function slotRolesFromRound(round, side) {
  return ((round && round[side]) || []).map((s) => (s && s.guid && HERO_ROLES[s.guid]) || null);
}

async function ocrCanvas(worker, cv) {
  const { data } = await worker.recognize(cv.toBuffer('image/png'));
  return data.text.trim();
}

async function reprocessSide(worker, cropPath) {
  const img = await loadImage(cropPath);
  const box = rebaseBox(img);
  const row = Nameplate.nameRow(img, box);
  if (!row) return null;
  const cw = box.w / 5;
  const reads = [];
  for (let i = 0; i < 5; i++) {
    const cell = { x: i * cw, y: box.y, w: cw, h: box.h };
    const cv = Nameplate.nameCrop(img, cell, row);
    reads.push(await ocrCanvas(worker, cv));
  }
  return reads;
}

function needsReprocess(attr, roster) {
  return SIDES.some((side) => {
    const ids = (attr[side] && attr[side].ids) || [];
    const hasNull = ids.some((id) => id === null || id === undefined);
    const hasRoster = ((roster && roster[side]) || []).length > 0;
    return hasNull && hasRoster;
  });
}

async function main() {
  console.log(`session: ${SESSION}${DRY ? '  (--dry, will not write)' : ''}\n`);
  const review = JSON.parse(fs.readFileSync(REVIEW_PATH, 'utf8'));

  const worker = await Tesseract.createWorker('eng');
  await worker.setParameters({
    tessedit_char_whitelist:
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
    // Matches run.js's worker config - see its comment. A name crop is one
    // word, and PSM 8 nearly tripled recovery over the default full-page
    // layout mode.
    tessedit_pageseg_mode: '8',
  });

  let scanned = 0, skippedCorrections = 0, candidateMaps = 0, reprocessedSides = 0,
    sideRowMissing = 0, recoveredSlots = 0, mapsWithRecovery = 0, mapsStillAbstained = 0,
    statusFlippedToReviewed = 0;
  const log = [];

  for (const m of review.maps) {
    scanned++;
    if (!m.attribution) continue;
    if ((m.corrections || []).length) { skippedCorrections++; continue; }
    const roster = m.roster || { a: [], b: [] };
    if (!needsReprocess(m.attribution, roster)) continue;
    candidateMaps++;

    const mapCode = String(path.basename(firstFramePath(m, 'a') || firstFramePath(m, 'b') || '').split('-')[0] || m.match_id);
    // Reuse attribute.js's own playersFor(), not the review artifact's
    // display-only `roster` field (id+name, no `role` - assign.js's role
    // constraint needs each player's registered role, which only the feed's
    // lineups carry). Matches production exactly, dual game_name/nick
    // matching included.
    const codeObj = { match_id: m.match_id, game_no: m.game_no, t1: m.side_a_team_id, t2: m.side_b_team_id };
    const t1players = Attribute.playersFor(FEED, codeObj, 'a');
    const t2players = Attribute.playersFor(FEED, codeObj, 'b');
    const oldReads = m.attribution.reads || { a: ['', '', '', '', ''], b: ['', '', '', '', ''] };
    const newReads = { a: oldReads.a.slice(), b: oldReads.b.slice() };

    const round = (m.rounds && m.rounds[0]) || null;
    const slotRoles = { a: slotRolesFromRound(round, 'a'), b: slotRolesFromRound(round, 'b') };

    for (const side of SIDES) {
      const ids = (m.attribution[side] && m.attribution[side].ids) || [];
      const hasNull = ids.some((id) => id === null || id === undefined);
      if (!hasNull || !(roster[side] || []).length) continue;
      const framePath = firstFramePath(m, side);
      if (!framePath) continue;
      const full = path.join(SESSION, framePath);
      if (!fs.existsSync(full)) continue;
      const got = await reprocessSide(worker, full);
      if (got) { newReads[side] = got; reprocessedSides++; }
      else sideRowMissing++;
    }

    const orient = Names.confidentOrientation(
      newReads.a, newReads.b, Attribute.rosterNames(t1players), Attribute.rosterNames(t2players));
    const swapped = orient === 'b';
    const leftTeam = swapped ? t2players : t1players;
    const rightTeam = swapped ? t1players : t2players;

    const newAttr = {
      a: Assign.assign(newReads.a, leftTeam, slotRoles.a),
      b: Assign.assign(newReads.b, rightTeam, slotRoles.b),
      orientation: orient === null ? null : (swapped ? 'swapped' : 'direct'),
      reads: newReads,
    };

    let mapRecovered = 0;
    SIDES.forEach((side) => {
      const oldIds = (m.attribution[side] && m.attribution[side].ids) || [null, null, null, null, null];
      const newIds = newAttr[side].ids;
      for (let i = 0; i < 5; i++) {
        if ((oldIds[i] === null || oldIds[i] === undefined) && newIds[i] != null) { recoveredSlots++; mapRecovered++; }
      }
    });
    if (mapRecovered > 0) mapsWithRecovery++; else mapsStillAbstained++;

    log.push({ code: mapCode, mapRecovered, oldReads, newReads, oldIds: { a: (m.attribution.a || {}).ids, b: (m.attribution.b || {}).ids }, newIds: { a: newAttr.a.ids, b: newAttr.b.ids } });

    m.attribution = newAttr;
    SIDES.forEach((side) => {
      (m.rounds || []).forEach((rd) => {
        (rd[side] || []).forEach((slot, i) => {
          const id = newAttr[side].ids[i], conf = newAttr[side].conf[i];
          slot.player_id = id;
          slot.player_conf = conf;
          const hadFlag = (slot.flags || []).indexOf('attribution-abstained') !== -1;
          const shouldFlag = id === null;
          if (shouldFlag && !hadFlag) slot.flags = (slot.flags || []).concat('attribution-abstained');
          if (!shouldFlag && hadFlag) slot.flags = (slot.flags || []).filter((f) => f !== 'attribution-abstained');
        });
      });
    });

    if (m.status === 'unreviewed') {
      const stillNeeds = Resolve.needsReview(m.rounds);
      if (!stillNeeds) { m.status = 'reviewed'; statusFlippedToReviewed++; }
    }
  }

  await worker.terminate();

  console.log(`scanned ${scanned} maps, ${skippedCorrections} skipped (human corrections already on them)`);
  console.log(`${candidateMaps} candidate maps (abstained slot + a roster to try), ${reprocessedSides} sides re-OCR'd (${sideRowMissing} still found no name row at all)`);
  console.log(`\nrecovered ${recoveredSlots} previously-null slots across ${mapsWithRecovery} maps; ${mapsStillAbstained} candidate maps still have at least one abstained slot`);
  console.log(`${statusFlippedToReviewed} maps flipped 'unreviewed' -> 'reviewed' now that nothing else flags them`);

  console.log('\nper-map detail (only maps that changed at least one slot):');
  log.filter((r) => r.mapRecovered > 0).forEach((r) => {
    console.log(`  ${r.code}: +${r.mapRecovered} slot(s)`);
    console.log(`    reads.a: ${JSON.stringify(r.oldReads.a)} -> ${JSON.stringify(r.newReads.a)}`);
    console.log(`    reads.b: ${JSON.stringify(r.oldReads.b)} -> ${JSON.stringify(r.newReads.b)}`);
  });

  console.log('\nper-map detail (candidates that STILL have an abstained slot after reprocessing):');
  log.filter((r) => r.mapRecovered === 0).forEach((r) => {
    console.log(`  ${r.code}: reads.a=${JSON.stringify(r.newReads.a)} reads.b=${JSON.stringify(r.newReads.b)}`);
  });

  if (DRY) {
    console.log('\n--dry: review artifact NOT written.');
    return;
  }
  const backup = REVIEW_PATH + '.bak-' + new Date().toISOString().replace(/[:.]/g, '-');
  fs.copyFileSync(REVIEW_PATH, backup);
  // Same format review_out.js's writeSession() uses (2-space indent, trailing
  // newline) - only `maps` actually changed, so session/built_at/feed_built_at
  // are left exactly as captured rather than stamped with "now", which would
  // misrepresent this as a fresh capture rather than a reprocessing pass.
  fs.writeFileSync(REVIEW_PATH, JSON.stringify(review, null, 2) + '\n', 'utf8');
  console.log(`\nbackup written to ${backup}`);
  console.log(`review artifact updated in place: ${REVIEW_PATH}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
