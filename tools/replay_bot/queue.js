// tools/replay_bot/queue.js
// Turning docs/capture/data.json's `codes` into the bot's work queue.
// See specs/2026-09-08-replay-bot-design.md §7.
//
// The thing this module exists to enforce: a replay code is not merely stale
// once its wipe has landed, it is GONE. Overwatch invalidates every code for a
// game finished on or before a patch's wipe date, and no amount of retrying
// brings one back. So a wiped code must never reach the driver - spending
// client time on it is not a slow path, it is a guaranteed failure.
//
// Note that every live code shares ONE expiry: the next wipe kills the whole
// queue at once, regardless of when each game finished. Ordering is therefore
// about determinism and resumability, not triage - there is no "expiring
// soonest" to prioritise.

(function (global) {
  'use strict';

  // The calendar day of an ISO timestamp, which is the granularity wipes are
  // recorded at.
  function day(iso) { return String(iso).slice(0, 10); }

  // How a captured map is named in `done`. A match has several games and each
  // is its own replay, so this is keyed per GAME - keying it on match_id alone
  // would silently skip every map after the first.
  function key(c) { return c.match_id + ':' + c.game_no; }

  // Codes still worth spending client time on, oldest game first. filter()
  // already copies, so the sort never disturbs the caller's feed.
  function pending(codes, opts) {
    var wipeDate = opts.wipeDate;
    var done = new Set(opts.done || []);
    return codes
      .filter(function (c) { return day(c.finished_at) > wipeDate; })
      .filter(function (c) { return !done.has(key(c)); })
      .sort(function (x, y) {
        return x.finished_at < y.finished_at ? -1 : x.finished_at > y.finished_at ? 1 : 0;
      });
  }

  var Mod = {
    day: day,
    pending: pending,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayQueue = Mod;
})(typeof self !== 'undefined' ? self : this);
