// tools/replay_bot/reprocess_hero_match.js
// Re-run hero-portrait matching against already-captured maps, now that
// docs/capture/refs.json is rebuilt from the correct (profile 7, replay)
// source instead of the live-spectate one it had silently reverted to on
// 2026-09-15 (see CHANGELOG). Targets maps captured inside that regression
// window - a bad hero match doesn't just mislabel its own slot, it can
// (assign.js's exact-role-cover check) discard perfectly good name reads for
// every other player in the same role group, so this redoes attribution too.
//
// This works from the SAVED CROP PNGs alone, not a live client, the same
// pattern reprocess_attribution.js already uses for name OCR:
// review_out.js's writeStrip() saves one portrait-band crop per round/side
// (the round's first kept sample) always, plus one crop PER SAMPLE
// (`<side>_samples` in `frames`) for any side a round's ORIGINAL resolution
// flagged as a mid-round swap. A round with no gallery is reprocessed from
// its single first-sample crop, on the same assumption resolve.js's own
// single-segment case already makes: a slot with only one available read
// held that hero for the whole tracked window. A round WITH a gallery is
// reprocessed sample-by-sample and fed through resolve.js's own segmentSlot
// (via Resolve.rounds), so a "swap" that was actually the old matcher
// flickering between two wrong heroes can collapse back into one segment
// exactly the way a live capture would have read it.
//
// A slot the ORIGINAL resolution already read as ABSENT_GUID/UNSELECTED_GUID
// is left untouched - those come from a tint check, not hero matching, and
// are unaffected by the bug this reprocesses.
//
// Usage: node tools/replay_bot/reprocess_hero_match.js <session> [--dry]
//   <session>  e.g. out/console-loop-2026-09-16T04-53-51-585Z (no .json)
//   --dry      compute and report, do not write the review/contribution back

'use strict';

const fs = require('fs');
const path = require('path');
const { loadImage } = require('@napi-rs/canvas');

const REPO = path.join(__dirname, '..', '..');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Match = require('./match.js');
const Resolve = require('./resolve.js');
const Attribute = require('./attribute.js');
const Assign = require(path.join(REPO, 'docs/capture/engine/assign.js'));
const Names = require(path.join(REPO, 'docs/capture/engine/names.js'));

const args = process.argv.slice(2).filter((a) => a !== '--dry');
const DRY = process.argv.includes('--dry');
const SESSION = args[0];
if (require.main === module && !SESSION) {
  console.log('usage: node tools/replay_bot/reprocess_hero_match.js <session> [--dry]');
  process.exit(1);
}
// review_out.js's mapEntry(io, sessionDir, ...) writes crops under
// path.join(sessionDir, 'crops') where sessionDir IS the session's own
// directory (e.g. out/console-loop-...-585Z/) - the SAME string as SESSION
// itself, not its parent.
const SESSION_DIR = SESSION;
const REVIEW_PATH = SESSION + '.review.json';
const SIDES = ['a', 'b'];
const PAD_Y = 12; // must match review_out.js's own PAD_Y

const FEED = JSON.parse(fs.readFileSync(path.join(REPO, 'docs', 'capture', 'data.json'), 'utf8'));
const HERO_ROLES = FEED.hero_roles || {};

const ABSENT_GUID = 'ABSENT';
const UNSELECTED_GUID = 'UNSELECTED';
const SENTINELS = new Set([ABSENT_GUID, UNSELECTED_GUID]);

const M = Match.make(require(path.join(REPO, 'docs/capture/refs.json')), { PAD: calib.FROZEN.ref.PAD });

// The five portrait cells, in the LOCAL coordinate frame of a writeStrip()
// crop (which is calib.FROZEN.boxes[side], shifted up by PAD_Y and rounded
// the same way writeStrip rounds its own crop rect) - not full-frame
// coordinates. Must mirror writeStrip's rounding exactly, or a cell lands a
// pixel or two off the portrait it is supposed to isolate.
function rebasedCells(side) {
  const box = calib.FROZEN.boxes[side];
  const ox = Math.round(box.x);
  const oy = Math.round(box.y) - PAD_Y;
  return calib.cells(side).map((c) => ({ x: c.x - ox, y: c.y - oy, w: c.w, h: c.h }));
}
const CELLS = { a: rebasedCells('a'), b: rebasedCells('b') };

// Re-match one saved strip crop's five slots. Returns [{name,guid,score} x5]
// or null if the file is missing/unreadable.
async function rematchStripFor(side, cropPath) {
  const full = path.join(SESSION_DIR, cropPath);
  if (!fs.existsSync(full)) return null;
  let img;
  try { img = await loadImage(full); } catch (e) { return null; }
  return CELLS[side].map((rect) => {
    const b64 = Crop.cell(img, rect, calib.FROZEN.ref);
    return M.match(b64, side);
  });
}

function slotRolesFromRound(round, side) {
  return ((round && round[side]) || []).map((s) => (s && s.guid && HERO_ROLES[s.guid]) || null);
}

// Reprocessing must never make an already-good read WORSE. review_out.js's
// mapEntry() only writes a round/side's per-sample gallery for samples that
// had a savable framePath at capture time - a sample lost then (no
// framePath) silently shrinks the gallery, with nothing on disk to say it
// happened. When the one surviving gallery sample falls inside resolve.js's
// ASSEMBLE_GRACE_S window, segmentSlot() correctly drops it as a pick-phase
// read, but with no other sample to fall back on the round/side goes from a
// real single-segment read to no-read - reprocessing has strictly LESS
// evidence than the live capture did (which saw frames never retained to
// disk), not new information. Found 2026-09-19 reprocessing the real corpus:
// 110 slot-rounds across 11 maps regressed to null this way before this
// guard existed.
//
// If ANY slot on a round's side went from a real guid to null, that whole
// round/side reverts to its ORIGINAL data (every live incident regressed
// all 5 slots together, since they share one sample set) - a genuine hero
// correction (guid changes but stays non-null) or a genuine recovery (null
// -> a guid) is untouched either way.
function guardAgainstRegression(originalRounds, newRounds) {
  return newRounds.map((round, ri) => {
    const orig = originalRounds[ri];
    if (!orig) return round;
    const out = Object.assign({}, round);
    SIDES.forEach((side) => {
      const regressed = (orig[side] || []).some((os, si) => {
        const ns = (round[side] || [])[si];
        return os && os.guid != null && ns && ns.guid == null;
      });
      if (regressed) out[side] = orig[side];
    });
    return out;
  });
}

async function reprocessMap(m, stats) {
  const frames = m.frames || {};
  const originalRounds = m.rounds || [];
  if (!originalRounds.length) return false;

  // One flat samples[] array across every round/side, in resolve.js's own
  // input shape - a sample object only populates the side(s) it actually has
  // data for, which resolve.js already tolerates (a missing side/slot reads
  // as no guid, not a crash).
  const samples = [];
  let anyChange = false;

  for (const round of originalRounds) {
    const pair = frames[String(round.round_no)];
    if (!pair) continue; // no crop at all for this round - leave it alone

    for (const side of SIDES) {
      const sentinelSlots = new Set();
      (round[side] || []).forEach((slot, i) => { if (SENTINELS.has(slot && slot.guid)) sentinelSlots.add(i); });

      const gallery = pair[side + '_samples'];
      let points; // [{t, cells:[{name,guid,score}x5] | null}]
      if (gallery && gallery.length) {
        points = [];
        for (const g of gallery) {
          const cells = await rematchStripFor(side, g.path);
          points.push({ t: g.t, cells });
        }
      } else if (pair[side]) {
        const cells = await rematchStripFor(side, pair[side]);
        // Synthetic single sample: any t past the grace window is
        // equivalent here (there is only one point), so this is not a real
        // capture time, only a placeholder resolve.js's grace filter accepts.
        points = [{ t: round.from_t + 15, cells }];
      } else {
        continue;
      }

      for (const p of points) {
        if (!p.cells) continue;
        const merged = p.cells.map((c, i) => (sentinelSlots.has(i)
          ? { name: round[side][i].name, guid: round[side][i].guid, score: null }
          : c));
        let entry = samples.find((s) => s.t === p.t);
        if (!entry) { entry = { t: p.t }; samples.push(entry); }
        entry[side] = merged;
        anyChange = true;
      }
    }
  }

  if (!anyChange) return false;

  // Attribution is resolved once per map, off round 1 (production's own
  // rule) - use round 1's freshly-rematched slot guids for the role
  // constraint, but the ORIGINAL OCR name reads (attribution.reads): this
  // bug never touched name recognition, only hero recognition, so there is
  // nothing to gain by re-OCRing and a real risk of a fresh tesseract pass
  // disagreeing with the human-reviewed original for no reason.
  let newAttribution = m.attribution || null;
  if (m.attribution && m.attribution.reads) {
    const round1 = originalRounds[0];
    const round1Samples = samples.filter((s) => s.t >= round1.from_t && s.t <= round1.to_t);
    const firstA = (round1Samples.find((s) => s.a) || {}).a;
    const firstB = (round1Samples.find((s) => s.b) || {}).b;
    const slotRoles = {
      a: firstA ? firstA.map((c) => (c && c.guid && HERO_ROLES[c.guid]) || null) : slotRolesFromRound(round1, 'a'),
      b: firstB ? firstB.map((c) => (c && c.guid && HERO_ROLES[c.guid]) || null) : slotRolesFromRound(round1, 'b'),
    };
    const codeObj = { match_id: m.match_id, game_no: m.game_no, t1: m.side_a_team_id, t2: m.side_b_team_id };
    const t1players = Attribute.playersFor(FEED, codeObj, 'a');
    const t2players = Attribute.playersFor(FEED, codeObj, 'b');
    const reads = m.attribution.reads;
    const orient = Names.confidentOrientation(
      reads.a, reads.b, Attribute.rosterNames(t1players), Attribute.rosterNames(t2players));
    const swapped = orient === 'b';
    const leftTeam = swapped ? t2players : t1players;
    const rightTeam = swapped ? t1players : t2players;
    newAttribution = {
      a: Assign.assign(reads.a, leftTeam, slotRoles.a),
      b: Assign.assign(reads.b, rightTeam, slotRoles.b),
      orientation: orient === null ? null : (swapped ? 'swapped' : 'direct'),
      reads: reads,
    };
  }

  const roundsMeta = originalRounds.map((r) => ({ from_t: r.from_t, to_t: r.to_t }));
  const rawNewRounds = Resolve.rounds(samples, roundsMeta, { heroRoles: HERO_ROLES, attribution: newAttribution });
  const newRounds = guardAgainstRegression(originalRounds, rawNewRounds);

  // Diff for the report, before overwriting.
  let heroesChanged = 0, abstainedBefore = 0, abstainedAfter = 0, regressionsGuarded = 0;
  SIDES.forEach((side) => {
    for (let r = 0; r < originalRounds.length; r++) {
      if (rawNewRounds[r][side] !== newRounds[r][side]) regressionsGuarded++;
      for (let slot = 0; slot < 5; slot++) {
        const before = (originalRounds[r][side] || [])[slot];
        const after = (newRounds[r][side] || [])[slot];
        if (before && after && before.guid !== after.guid) heroesChanged++;
        if (before && (before.flags || []).includes('attribution-abstained')) abstainedBefore++;
        if (after && (after.flags || []).includes('attribution-abstained')) abstainedAfter++;
      }
    }
  });

  stats.heroesChanged += heroesChanged;
  stats.abstainedBefore += abstainedBefore;
  stats.abstainedAfter += abstainedAfter;
  stats.regressionsGuarded += regressionsGuarded;
  if (heroesChanged > 0 || abstainedAfter < abstainedBefore) stats.mapsImproved++;
  stats.log.push({ code: m.demo_code, heroesChanged, abstainedBefore, abstainedAfter, regressionsGuarded });

  m.rounds = newRounds;
  m.attribution = newAttribution;
  if (m.status === 'unreviewed' && !Resolve.needsReview(newRounds)) m.status = 'reviewed';
  return true;
}

async function main() {
  console.log(`session: ${SESSION}${DRY ? '  (--dry, will not write)' : ''}\n`);
  const review = JSON.parse(fs.readFileSync(REVIEW_PATH, 'utf8'));

  const stats = { heroesChanged: 0, abstainedBefore: 0, abstainedAfter: 0, mapsImproved: 0, regressionsGuarded: 0, log: [] };
  let scanned = 0, reprocessed = 0;

  for (const m of review.maps) {
    scanned++;
    const changed = await reprocessMap(m, stats);
    if (changed) reprocessed++;
  }

  console.log(`scanned ${scanned} maps, ${reprocessed} reprocessed (had at least one usable crop)`);
  console.log(`hero guid changed on ${stats.heroesChanged} slot-rounds`);
  console.log(`attribution-abstained flags: ${stats.abstainedBefore} -> ${stats.abstainedAfter}`);
  console.log(`${stats.mapsImproved} maps improved (a hero corrected or an abstention recovered)`);
  if (stats.regressionsGuarded) {
    console.log(`${stats.regressionsGuarded} round/side(s) would have regressed to no-read (incomplete ` +
      `recovered gallery) - kept their original data instead of overwriting`);
  }

  console.log('\nper-map detail (only maps that changed):');
  stats.log.filter((r) => r.heroesChanged > 0 || r.abstainedAfter !== r.abstainedBefore || r.regressionsGuarded > 0).forEach((r) => {
    console.log(`  ${r.code}: heroes changed=${r.heroesChanged}, abstained ${r.abstainedBefore} -> ${r.abstainedAfter}` +
      (r.regressionsGuarded ? `, regressions guarded=${r.regressionsGuarded}` : ''));
  });

  if (DRY) {
    console.log('\n--dry: review artifact NOT written.');
    return;
  }
  const backup = REVIEW_PATH + '.bak-' + new Date().toISOString().replace(/[:.]/g, '-');
  fs.copyFileSync(REVIEW_PATH, backup);
  fs.writeFileSync(REVIEW_PATH, JSON.stringify(review, null, 2) + '\n', 'utf8');
  console.log(`\nbackup written to ${backup}`);
  console.log(`review artifact updated in place: ${REVIEW_PATH}`);
}

module.exports = { reprocessMap, guardAgainstRegression };

if (require.main === module) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
