// tools/replay_bot/prune_frames.js
// Frame retention. frames/ is a flat, run-shared directory (filenames restart
// at 0 every run - see frames/README.md), so there is no per-map subdirectory
// to key deletion off a review's per-slot flags without touching the tuned
// capture path. This is the coarser policy that needs no such change:
//
//   node tools/replay_bot/prune_frames.js [<session>]
//
// 1. Load out/<session>.review.json (newest by default, same convention as
//    review/server.js). If EVERY map in it has zero flags on every slot of
//    every round, nothing in the run needs re-reading - wipe frames/ (except
//    frames/corpus/, the hand-copied labelled witnesses, and the README).
//    If ANY map has a flag, leave frames/ alone entirely.
// 2. Regardless of (1), delete anything in frames/ (again excluding corpus/)
//    older than 30 days - a backstop against a review that never gets acted
//    on.
'use strict';

const fs = require('fs');
const path = require('path');

const RBOT = __dirname;
const OUT = path.join(RBOT, 'out');
const FRAMES = path.join(RBOT, 'frames');
const KEEP = new Set(['corpus', 'README.md', '.gitignore']);
const BACKSTOP_MS = 30 * 24 * 60 * 60 * 1000;

function newestReview(dir) {
  let best = null, bestAt = -1;
  for (const f of (fs.existsSync(dir) ? fs.readdirSync(dir) : [])) {
    if (!f.endsWith('.review.json')) continue;
    const at = fs.statSync(path.join(dir, f)).mtimeMs;
    if (at > bestAt) { bestAt = at; best = path.join(dir, f); }
  }
  return best;
}

function reviewHasAnyFlag(review) {
  for (const m of review.maps || []) {
    for (const r of m.rounds || []) {
      for (const side of ['a', 'b']) {
        for (const slot of r[side] || []) {
          if (slot && slot.flags && slot.flags.length) return true;
        }
      }
    }
  }
  return false;
}

function wipeFrames() {
  let n = 0;
  for (const f of fs.readdirSync(FRAMES)) {
    if (KEEP.has(f)) continue;
    fs.rmSync(path.join(FRAMES, f), { recursive: true, force: true });
    n++;
  }
  return n;
}

function backstop() {
  const cutoff = Date.now() - BACKSTOP_MS;
  let n = 0;
  for (const f of fs.readdirSync(FRAMES)) {
    if (KEEP.has(f)) continue;
    const p = path.join(FRAMES, f);
    if (fs.statSync(p).mtimeMs < cutoff) {
      fs.rmSync(p, { recursive: true, force: true });
      n++;
    }
  }
  return n;
}

function main() {
  const arg = process.argv[2];
  const reviewPath = arg
    ? (arg.endsWith('.review.json') ? path.join(OUT, arg) : path.join(OUT, arg + '.review.json'))
    : newestReview(OUT);

  if (!reviewPath || !fs.existsSync(reviewPath)) {
    console.log('no review.json found - running backstop sweep only');
  } else {
    const review = JSON.parse(fs.readFileSync(reviewPath, 'utf8'));
    if (reviewHasAnyFlag(review)) {
      console.log(`${path.basename(reviewPath)} has flagged slots - leaving frames/ alone`);
    } else {
      const n = wipeFrames();
      console.log(`${path.basename(reviewPath)} is clean - wiped ${n} item(s) from frames/`);
    }
  }

  const swept = backstop();
  if (swept) console.log(`backstop: removed ${swept} item(s) older than 30 days`);
}

main();
