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
    var done = new Set(opts.done || []);
    var dir = opts.newestFirst ? -1 : 1;
    return codes
      .filter(function (c) { return day(c.finished_at) > wipeDate; })
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
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayQueue = Mod;
})(typeof self !== 'undefined' ? self : this);
