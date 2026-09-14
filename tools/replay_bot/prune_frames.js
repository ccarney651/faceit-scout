// tools/replay_bot/prune_frames.js
// Frame retention. frames/ is a flat, run-shared directory (filenames restart
// at 0 every run - see frames/README.md), so there is no per-map subdirectory
// to key deletion off a review's per-slot flags without touching the tuned
// capture path. This is the policy that needs no such change:
//
//   node tools/replay_bot/prune_frames.js [<session>] [--dry]
//
// 1. Load out/<session>.review.json (newest by default, same convention as
//    review/server.js). If EVERY map in it has zero flags on every slot of
//    every round, nothing in the run needs re-reading - wipe frames/ (except
//    frames/corpus/, the hand-copied labelled witnesses, the README, the
//    .gitignore, and the golden bootstrap frame README documents).
//    If ANY map has a flag, the run still needs its frames - but only the
//    sample frames (cap-t<seconds>-<n>.png) of the session it belongs to,
//    which are the only frames a better matcher would re-read. Since the 30s
//    cadence + change-detection retention, those sample frames are one per
//    COMP CHANGE (a kept frame is one whose read differed from the previous),
//    not one per grid point - so a session's kept set is exactly the recovery
//    value: sparse, and aimed at the reads that went wrong. Every frame
//    from an older session (whose review no longer exists - out/ is cleaned),
//    every non-sample tag (settle/probe/panel/q/bar/timeline/media/pause/... -
//    seek and settle debris, no re-read needs it) and every experiment scratch
//    frame is deleted. A session's window is [local midnight of its date,
//    mtime of its review + slack], so nothing the review can still point at is
//    lost. When an explicit session is given, the newest review's sample
//    frames are also kept - an old session arg is a cleanup request, and the
//    newest recovery value is the point of keeping frames at all.
// 2. Regardless of (1), delete anything in frames/ (again excluding the keeps)
//    older than 30 days - a backstop against a review that never gets acted
//    on.
//
// --dry prints what would be removed without removing it.
'use strict';

const fs = require('fs');
const path = require('path');

const RBOT = __dirname;
const OUT = path.join(RBOT, 'out');
const FRAMES = path.join(RBOT, 'frames');
const KEEP = new Set(['corpus', 'README.md', '.gitignore', '2026-09-08-busan-2560x1440.png']);
const BACKSTOP_MS = 30 * 24 * 60 * 60 * 1000;
// The sample frames a better matcher would re-read: cap-t<seconds>-<n>.png,
// kept by capture.js keepAs() under change-detection - one per comp change,
// not one per grid point. Everything else under cap-* is scratch.
const SAMPLE = /^cap-t\d+-\d+\.png$/;
// Slack on the end of a session's window: frames for the last map are written
// just before the review, and clock wobble has been seen before.
const END_SLACK_MS = 12 * 60 * 60 * 1000;

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

// The [start, end] window of frame mtimes a session owns, or null when the
// session name carries no date (then nothing can be attributed to it).
function sessionWindowMs(review, reviewPath) {
  const name = review.session || path.basename(reviewPath).replace(/\.review\.json$/, '');
  const m = /(\d{4})-(\d{2})-(\d{2})/.exec(name);
  if (!m) return null;
  const start = new Date(+m[1], +m[2] - 1, +m[3]).getTime();
  const end = fs.statSync(reviewPath).mtimeMs + END_SLACK_MS;
  return { start, end };
}

function inWindow(st, win) {
  return st.mtimeMs >= win.start && st.mtimeMs <= win.end;
}

function wipeFrames(dry) {
  let n = 0;
  for (const f of fs.readdirSync(FRAMES)) {
    if (KEEP.has(f)) continue;
    if (dry) { console.log('  would remove ' + f); }
    else fs.rmSync(path.join(FRAMES, f), { recursive: true, force: true });
    n++;
  }
  return n;
}

// Keep only sample frames inside the session window(s); remove everything else.
function pruneToSamples(win, extraWin, dry) {
  let removed = 0, kept = 0;
  for (const f of fs.readdirSync(FRAMES)) {
    if (KEEP.has(f)) continue;
    const p = path.join(FRAMES, f);
    const st = fs.statSync(p);
    const keep = SAMPLE.test(f) && (inWindow(st, win) || (extraWin && inWindow(st, extraWin)));
    if (keep) { kept++; continue; }
    if (dry) console.log('  would remove ' + f);
    else fs.rmSync(p, { recursive: true, force: true });
    removed++;
  }
  return { removed, kept };
}

function backstop(dry) {
  const cutoff = Date.now() - BACKSTOP_MS;
  let n = 0;
  for (const f of fs.readdirSync(FRAMES)) {
    if (KEEP.has(f)) continue;
    const p = path.join(FRAMES, f);
    if (fs.statSync(p).mtimeMs < cutoff) {
      if (dry) console.log('  backstop would remove ' + f);
      else fs.rmSync(p, { recursive: true, force: true });
      n++;
    }
  }
  return n;
}

function main() {
  const args = process.argv.slice(2);
  const dry = args.includes('--dry');
  const arg = args.find((a) => !a.startsWith('--'));
  const reviewPath = arg
    ? (arg.endsWith('.review.json') ? path.join(OUT, arg) : path.join(OUT, arg + '.review.json'))
    : newestReview(OUT);

  if (!reviewPath || !fs.existsSync(reviewPath)) {
    console.log('no review.json found - running backstop sweep only');
  } else {
    const review = JSON.parse(fs.readFileSync(reviewPath, 'utf8'));
    const win = sessionWindowMs(review, reviewPath);
    let extraWin = null;
    const newest = newestReview(OUT);
    if (newest && newest !== reviewPath) {
      extraWin = sessionWindowMs(JSON.parse(fs.readFileSync(newest, 'utf8')), newest);
    }

    if (reviewHasAnyFlag(review)) {
      if (!win) {
        console.log(`${path.basename(reviewPath)} has flagged slots but its session name has no date - leaving frames/ alone`);
      } else {
        const r = pruneToSamples(win, extraWin, dry);
        console.log(`${dry ? 'would keep' : 'kept'} ${r.kept} sample frame(s), ${dry ? 'would remove' : 'removed'} ${r.removed} item(s) from frames/`);
      }
    } else {
      const n = wipeFrames(dry);
      console.log(`${path.basename(reviewPath)} is clean - ${dry ? 'would wipe' : 'wiped'} ${n} item(s) from frames/`);
    }
  }

  const swept = backstop(dry);
  if (swept) console.log(`${dry ? 'backstop would remove' : 'backstop removed'} ${swept} item(s) older than 30 days`);
}

main();