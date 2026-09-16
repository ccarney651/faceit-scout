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
// queue at once, regardless of when each game finished. So there is no
// "expiring soonest" to prioritise, and ordering within the queue is about
// determinism and resumability.
//
// TRIAGE STILL MATTERS, THOUGH, AND FOR A DIFFERENT REASON: the queue does not
// reliably FIT. The league produces about 127 coded games a day across every
// region and tier, which is around nine hours of capture a week against a patch
// cadence of roughly one - and those nine hours are hours the client cannot be
// used for anything else. When the whole queue will not finish before the wipe,
// which codes get the client's time is the entire question, so this filters by
// division and by team.

(function (global) {
  'use strict';

  // The calendar day of an ISO timestamp, which is the granularity wipes are
  // recorded at.
  function day(iso) { return String(iso).slice(0, 10); }

  // How a captured map is named in `done`. A match has several games and each
  // is its own replay, so this is keyed per GAME - keying it on match_id alone
  // would silently skip every map after the first.
  function key(c) { return c.match_id + ':' + c.game_no; }

  function norm(s) { return String(s === null || s === undefined ? '' : s).toLowerCase(); }

  // The region a division string belongs to - "NA Master" -> "NA". Curated
  // text, but every division the feed emits is "<REGION> <TIER>" (see
  // tools/build_capture_data.py), so the first word is always it.
  function regionOf(division) { return String(division || '').split(' ')[0]; }

  // A patch's server restart does not land in every region at the same real
  // moment, but docs/capture/data.json carries ONE global code_wipe_date -
  // dated to whichever region's patch landed EARLIEST, so that region's
  // same-day post-patch games stay queueable (see owdb/db.py's _SEED_WIPES
  // comments on deliberate day-early dating). A region whose own restart
  // landed LATER in its own calendar day needs a stricter, region-specific
  // date on top of that global one, or its wipe-day games look alive when
  // they are not.
  //
  // This module stays a pure, general-purpose filter - it does not hardcode
  // any region's dates itself. `regionWipeDates` (e.g. run.js's
  // REGION_WIPE_OVERRIDES, the hand-maintained, dated, _SEED_WIPES-style
  // record of when) is an explicit, optional opt-in so a test exercising an
  // unrelated wipeDate is never silently affected by a later patch's facts.
  //
  // The effective wipe date for one code: the later (stricter) of the global
  // date and this code's region's override, if any. Exported so a caller can
  // ask "is this code dead?" the same way pending() itself decides, without
  // re-deriving the region/override logic - see prune_expired_attempts.js.
  function effectiveWipeDate(code, wipeDate, regionWipeDates) {
    var override = regionWipeDates && regionWipeDates[regionOf(code.division)];
    if (!override) return wipeDate;
    return override > wipeDate ? override : wipeDate;
  }

  function isDead(code, wipeDate, regionWipeDates) {
    return !(day(code.finished_at) > effectiveWipeDate(code, wipeDate, regionWipeDates));
  }

  // Loose, so "EMEA" takes every EMEA tier and "EMEA Master" takes just the one.
  // A division name is curated text, not an identifier, and asking an operator
  // to type it exactly is how a filter silently matches nothing.
  function matchesAny(value, wanted) {
    if (!wanted || !wanted.length) return true;
    var v = norm(value);
    return wanted.some(function (w) { return v.indexOf(norm(w)) !== -1; });
  }

  // Codes still worth spending client time on.
  //
  // Oldest game first by default: deterministic, and a resumed run picks up
  // where it stopped. `newestFirst` is for when the queue will not finish and
  // the freshest games are the ones worth having. Either way a match's four or
  // five games share a timestamp and stay adjacent, which is what makes the
  // output read as "this team, this match" rather than scattered maps.
  //
  // filter() already copies, so the sort never disturbs the caller's feed.
  function pending(codes, opts) {
    var wipeDate = opts.wipeDate;
    var regionWipeDates = opts.regionWipeDates;
    var done = new Set(opts.done || []);
    var dir = opts.newestFirst ? -1 : 1;
    return codes
      .filter(function (c) { return !isDead(c, wipeDate, regionWipeDates); })
      .filter(function (c) { return !done.has(key(c)); })
      .filter(function (c) { return matchesAny(c.division, opts.divisions); })
      .filter(function (c) {
        if (!opts.teams || !opts.teams.length) return true;
        return matchesAny(c.team_a, opts.teams) || matchesAny(c.team_b, opts.teams);
      })
      .sort(function (x, y) {
        if (x.finished_at === y.finished_at) return 0;
        return (x.finished_at < y.finished_at ? -1 : 1) * dir;
      });
  }

  var Mod = {
    day: day,
    matchesAny: matchesAny,
    pending: pending,
    regionOf: regionOf,
    effectiveWipeDate: effectiveWipeDate,
    isDead: isDead,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayQueue = Mod;
})(typeof self !== 'undefined' ? self : this);
