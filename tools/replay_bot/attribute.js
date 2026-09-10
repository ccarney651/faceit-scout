// tools/replay_bot/attribute.js
// Which FACEIT player is in which of a map's ten HUD slots.
// See specs/2026-09-10-replay-bot-player-attribution-design.md.
//
// Resolved ONCE PER MAP, off the frame the map's first sample already read -
// not per sample, not per round. Replay HUDs are static per slot for the life
// of a map, so one resolution serves every observation it produces.
//
// docs/capture/engine/assign.js is required directly, unmodified: it is pure
// (§1 of the design), and it already degrades exactly the way this needs to
// without any special-casing here. Missing lineups for a side becomes an
// empty players array, which leaves every role's pool empty and every slot
// null - the same shape a role mismatch already produces. A frame whose name
// row could not be found becomes five empty-string reads, which still lets
// assign() resolve a slot by role ALONE where the constraint is exact - "the
// tank is determined with no name evidence at all" is not a fallback path,
// it is assign()'s ordinary behaviour, so nothing here needs to reproduce it.

(function (global) {
  'use strict';

  var calib = require('./calib.js');
  var Nameplate = require('./nameplate.js');
  var Assign = require('../../docs/capture/engine/assign.js');

  var SIDES = ['a', 'b'];
  var BLANK_READS = ['', '', '', '', ''];

  // This game's five players for one side, in assign()'s shape - or [] when
  // the feed has no lineup for this code (an ad-hoc/synthesised code, or a
  // stale feed): assign() already treats an empty pool as "abstain every
  // slot," so that is left to do the work rather than special-cased here.
  //
  // Players carry both a Battle.net game_name and a FACEIT nick, and checking
  // only one throws away a free second chance (assign.js's own scoreRead
  // already tries every name in the list).
  function playersFor(feed, code, side) {
    var key = code.match_id + ':' + code.game_no;
    var lineup = feed.lineups && feed.lineups[key];
    if (!lineup) return [];
    var teamId = side === 'a' ? code.t1 : code.t2;
    var team = lineup[teamId];
    if (!team || !team.players) return [];
    return team.players.map(function (p) {
      return { id: p.id, names: [p.game_name, p.nick].filter(Boolean), role: p.role };
    });
  }

  // The role of the hero already recognised in each of a side's five slots,
  // from the feed's guid->role map. A hero the feed has never heard of
  // (freshly added, or an operator's custom hero) yields null for that slot -
  // the same "cannot place by role" outcome a genuine role mismatch produces,
  // never a guess.
  function slotRolesFor(heroRoles, reads) {
    return reads.map(function (r) { return (r && r.guid && heroRoles[r.guid]) || null; });
  }

  // ocr(canvas) -> Promise<string>, injected so a test can supply canned
  // strings instead of a real tesseract worker - the same shape `io` is
  // injected into capture.js throughout the rest of the bot.
  function make(ocr) {
    async function attributeMap(img, sample, feed, code) {
      var heroRoles = feed.hero_roles || {};
      var out = {};

      for (var s = 0; s < SIDES.length; s++) {
        var side = SIDES[s];
        var box = calib.FROZEN.boxes[side];
        var row = Nameplate.nameRow(img, box);
        var slotCells = calib.slots(side);

        var reads;
        if (row) {
          reads = [];
          for (var i = 0; i < slotCells.length; i++) {
            reads.push(await ocr(Nameplate.nameCrop(img, slotCells[i], row)));
          }
        } else {
          reads = BLANK_READS.slice();
        }

        var players = playersFor(feed, code, side);
        var slotRoles = slotRolesFor(heroRoles, sample[side]);
        out[side] = Assign.assign(reads, players, slotRoles);
      }

      return out;
    }

    return { attributeMap: attributeMap };
  }

  var Mod = { make: make, playersFor: playersFor, slotRolesFor: slotRolesFor };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayAttribute = Mod;
})(typeof self !== 'undefined' ? self : this);
