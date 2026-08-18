// docs/capture/engine/assign.js
// Which FACEIT player is in which HUD slot — see
// specs/2026-08-16-player-assignment-design.md.
//
// The old matcher (index.html's attribute()) asked only "which roster name does
// this OCR read look like?", so a team whose Battle.net names OCR badly got no
// attribution at all. This one starts from a constraint instead of a guess:
//
//   Overwatch tournament play is ROLE LOCKED, and FACEIT records the role each
//   player queued for, per game. Measured over the whole database, 8303 of 8356
//   team-games are exactly 1 Tank / 2 Damage / 2 Support (99.37%) - and every
//   one of the 53 exceptions is a MISSING role, never a real 2-tank comp.
//
// The role of the hero recognised in a slot therefore says which players can
// possibly be standing in it. A correctly-read comp collapses from 120
// permutations to 1 x 2 x 2 = 4, and THE TANK IS DETERMINED WITH NO NAME
// EVIDENCE AT ALL. That is the same reduction owdb/match.py already applies to
// hero matching ("a tank slot becomes a 1-of-14 decision instead of 1-of-52"),
// pointed at players instead.
//
// Measured against 8303 real lineups with synthetic OCR corruption
// (tools/assign_eval.py), at 30% character error this tags 98.9% of slots
// correctly where the old matcher managed 63.5%; at 50%, 86.0% vs 23.5%. With
// the names contributing NOTHING it still gets 20% right - the tank - and, at
// FLOOR 45, none wrong.
//
// Works as a browser global (`window.OWDBAssign`) and as a CommonJS module.

(function (global) {
  'use strict';

  var Names = (typeof module !== 'undefined' && module.exports)
    ? require('./names.js') : global.OWDBNames;

  // Both gates below are measured, not guessed - see the design doc's table.
  //
  // FLOOR is the load-bearing one and it is not cosmetic. Without it (FLOOR=0)
  // the very same resolver produced 33.6% WRONG assignments once the reads went
  // to garbage, because uniform noise reliably manufactures a score lead between
  // two candidates. With it, the wrong-assignment rate is 0.0% everywhere in the
  // operating range. FLOOR 60 is strictly worse than 45 (56.9% vs 85.5% correct
  // at 50% error under the mean-only gate, both zero wrong); FLOOR 30 puts 1.5%
  // wrong back on the table.
  //
  // Provisional: the corruption model is uniform independent per-character
  // noise, and real tesseract errors are systematic and correlated. Re-derive
  // both from real reads once playersRaw has collected some (design doc 7).
  var FLOOR = 45;    // mean per-slot score required before a contested group is assigned
  var MARGIN = 1;    // the winning permutation must actually beat the runner-up

  var ROLES = ['Tank', 'Damage', 'Support'];

  function normRole(r) {
    if (r == null) return null;
    var s = String(r).trim().toLowerCase();
    for (var i = 0; i < ROLES.length; i++) {
      if (ROLES[i].toLowerCase() === s) return ROLES[i];
    }
    return null;                       // FACEIT's '-' sentinel, or anything odd
  }

  // Best score of one OCR read against every alias a player carries. Players
  // carry BOTH a Battle.net game_name and a FACEIT nick and they differ for most
  // of the league, so checking only one throws away a free second chance.
  function scoreRead(read, player) {
    var best = 0, names = player && player.names || [];
    for (var i = 0; i < names.length; i++) {
      var s = Names.simScore(read || '', names[i]);
      if (s > best) best = s;
    }
    return best;
  }

  function permutations(items) {
    if (items.length <= 1) return [items.slice()];
    var out = [];
    for (var i = 0; i < items.length; i++) {
      var rest = items.slice(0, i).concat(items.slice(i + 1));
      var sub = permutations(rest);
      for (var j = 0; j < sub.length; j++) out.push([items[i]].concat(sub[j]));
    }
    return out;
  }

  // assign(reads, players, slotRoles, opts)
  //   reads     - [string x5], the OCR read per HUD slot ('' when unreadable)
  //   players   - [{id, names:[...], role}], THIS GAME's five (see the `lineups`
  //               feed key - a per-MATCH roster is wrong here, 27% of them carry
  //               more than five players once substitutes are counted)
  //   slotRoles - [role|null x5], the role of the hero recognised in each slot
  //
  // Returns { ids: [id|null x5], conf: [conf|null x5] } where conf is:
  //   'forced'  - determined by the role constraint alone, no name evidence used
  //   'matched' - cleared both the margin and the floor
  //   null      - abstained; the caller leaves the slot for the operator
  function assign(reads, players, slotRoles, opts) {
    var o = opts || {};
    var floor = o.floor === undefined ? FLOOR : o.floor;
    var margin = o.margin === undefined ? MARGIN : o.margin;
    var ids = [null, null, null, null, null];
    var conf = [null, null, null, null, null];
    reads = reads || []; players = players || []; slotRoles = slotRoles || [];

    for (var r = 0; r < ROLES.length; r++) {
      var role = ROLES[r];
      var slots = [], pool = [], i;
      for (i = 0; i < 5; i++) if (normRole(slotRoles[i]) === role) slots.push(i);
      for (i = 0; i < players.length; i++) {
        if (players[i] && players[i].id && normRole(players[i].role) === role) pool.push(players[i]);
      }
      // Exact cover or nothing. A mismatch means either a misrecognised portrait
      // (owdb/match.py's roles_consistent check, same reasoning) or a player whose
      // role never came through - both are reasons to leave this group to the
      // operator, not to force a body into a slot.
      if (!slots.length || slots.length !== pool.length) continue;

      var perms = permutations(pool), scored = [];
      for (i = 0; i < perms.length; i++) {
        var total = 0;
        for (var k = 0; k < slots.length; k++) total += scoreRead(reads[slots[k]], perms[i][k]);
        scored.push({ total: total, perm: perms[i] });
      }
      scored.sort(function (a, b) { return b.total - a.total; });
      var best = scored[0];

      var how;
      if (scored.length === 1) {
        // One role, one player: the constraint alone settles it. This is the
        // tank, and it is why a completely unreadable HUD still yields 20%.
        how = 'forced';
      } else if (best.total - scored[1].total < margin) {
        continue;                                    // nothing separates the orderings
      } else {
        // The group mean is the general gate, but ONE decisive read is enough on
        // its own: if a slot matches a player outright, its partner follows by
        // elimination, and the mean must not veto that.
        //
        // This is not a hypothetical. On a real frame (2026-07-15 231549)
        // "TWERKNATION" read at 88 while its support partner "PROXY" came back as
        // "H0Qf" - tesseract failing outright on a crop that is perfectly legible
        // by eye. The mean fell to just under FLOOR and BOTH slots abstained,
        // losing a slot the old name-only matcher got right.
        //
        // Real OCR fails per NAME, not per character: one read is pristine and the
        // next is destroyed. tools/assign_eval.py models uniform per-character
        // noise, which degrades all five together and so barely exercises this at
        // all (+0.5pp there, two slots on the real frame). It measures the safety
        // that matters though - the wrong-assignment rate is IDENTICAL with and
        // without this clause at every error level.
        var perSlot = 0;
        for (i = 0; i < slots.length; i++) {
          perSlot = Math.max(perSlot, scoreRead(reads[slots[i]], best.perm[i]));
        }
        var decisive = perSlot >= (Names && Names.STRONG_NAME_SCORE || 75);
        if (best.total / slots.length < floor && !decisive) continue;
        how = 'matched';
      }
      for (i = 0; i < slots.length; i++) {
        ids[slots[i]] = best.perm[i].id;
        conf[slots[i]] = how;
      }
    }
    return { ids: ids, conf: conf };
  }

  var Mod = {
    assign: assign,
    normRole: normRole,
    scoreRead: scoreRead,
    permutations: permutations,
    FLOOR: FLOOR,
    MARGIN: MARGIN,
    ROLES: ROLES,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBAssign = Mod;
})(typeof self !== 'undefined' ? self : this);
