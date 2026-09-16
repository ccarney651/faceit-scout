// tools/replay_bot/prune_expired_attempts.js
// Removes state/attempts.json entries for codes that are now dead - per the
// same wipeDate + REGION_WIPE_OVERRIDES calculation queue.js's pending() uses
// to decide what to queue - so a code that was attempted before a wipe (or a
// regional wipe-timing correction) was known stops cluttering the Failures
// panel and the "needs manual attention" list forever with something that can
// never be retried.
//
//   node tools/replay_bot/prune_expired_attempts.js          removes them
//   node tools/replay_bot/prune_expired_attempts.js --dry    lists, touches nothing
//
// Re-runnable any time: an attempt for a code that's still alive is left
// alone, and a key with no match in the feed at all (an ad-hoc/test code,
// which was never a real league game) is left alone too - this is only for
// entries the feed itself can confirm are dead.

const fs = require('fs');
const path = require('path');

const Q = require('./queue.js');
const RunJS = require('./run.js');

const STATE = path.join(__dirname, 'state', 'attempts.json');
const FEED = path.join(__dirname, '../../docs/capture/data.json');

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

// Pure, for testing: given the feed and the attempts ledger, which keys are
// for now-dead codes.
function expiredKeys(feed, attempts) {
  const byKey = {};
  ((feed && feed.codes) || []).forEach((c) => { byKey[c.match_id + ':' + c.game_no] = c; });
  return Object.keys(attempts || {}).filter((key) => {
    const fc = byKey[key];
    if (!fc) return false;   // not in the feed at all - not what this is for
    return Q.isDead(fc, feed.code_wipe_date, RunJS.REGION_WIPE_OVERRIDES);
  });
}

function main() {
  const dry = process.argv.includes('--dry');
  const feed = readJson(FEED, null);
  if (!feed) throw new Error('no feed at ' + FEED);
  const attempts = readJson(STATE, {});
  const byKey = {};
  (feed.codes || []).forEach((c) => { byKey[c.match_id + ':' + c.game_no] = c; });

  const toRemove = expiredKeys(feed, attempts);
  if (!toRemove.length) { console.log('nothing expired to remove'); return; }

  toRemove.forEach((key) => {
    const a = attempts[key], fc = byKey[key];
    console.log(`${dry ? '(dry) would remove' : 'removing'}: ${key}  ${a.code}  ` +
      `${fc.division}  ${fc.finished_at}  (was ${a.status})`);
  });

  if (dry) { console.log(`\n--dry: ${toRemove.length} would be removed`); return; }

  toRemove.forEach((key) => { delete attempts[key]; });
  fs.writeFileSync(STATE, JSON.stringify(attempts, null, 2) + '\n');
  console.log(`\nremoved ${toRemove.length} expired attempt(s)`);
}

module.exports = { expiredKeys };

if (require.main === module) main();
