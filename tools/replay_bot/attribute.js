// tools/replay_bot/attribute.js
// Which FACEIT player is in which of a map's ten HUD slots.
// See specs/2026-09-17-replay-bot-disconnect-identity-design.md.
//
// Resolved from EVERY sample a map produced, not one frame - a disconnect
// mid-round compacts the HUD's slot grid (specs/2026-09-17-...-design.md §0),
// so a single frame's read can no longer be trusted to key hero data by
// visual position. This module runs once, in a batch, after a map's samples
// are all collected: it establishes each side's canonical player_id->slot
// mapping from every sample's name-matches, then re-keys every sample's
// hero-cell array from visual position into canonical slot order.
//
// Pure and synchronous - no image loading or OCR here. Names are already-
// extracted text by the time this runs (phases.readNames, captured once per
// sample at capture time). docs/capture/engine/assign.js is required
// directly, unmodified: it is pure and already degrades exactly the way this
// needs to without any special-casing here. Missing lineups for a side
// becomes an empty players array, which leaves every role's pool empty and
// every slot null - the same shape a role mismatch already produces. A
// sample whose name row could not be found becomes five empty-string reads,
// which still lets assign() resolve a slot by role ALONE where the
// constraint is exact - "the tank is determined with no name evidence at
// all" is not a fallback path, it is assign()'s ordinary behaviour, so
// nothing here needs to reproduce it.

(function (global) {
  'use strict';

  var Assign = require('../../docs/capture/engine/assign.js');
  var Names = require('../../docs/capture/engine/names.js');

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

  // Every name string a roster can be matched against - both the Battle.net
  // game_name (what the HUD shows) and the FACEIT nick (which can read nothing
  // like it). names.js's affinity takes the max over the whole list, so a
  // player matches on whichever one OCR came closest to.
  function rosterNames(players) {
    var out = [];
    players.forEach(function (p) { (p.names || []).forEach(function (n) { if (n) out.push(n); }); });
    return out;
  }

  // Every sample's per-side {ids, conf} from Assign.assign, run once per
  // sample instead of once per map (same call attributeMap used to make once
  // per map, just made more often - see design doc §4).
  function perSampleAssign(samples, leftTeam, rightTeam, heroRoles) {
    return samples.map(function (s) {
      var namesA = (s.names && s.names.a) || BLANK_READS;
      var namesB = (s.names && s.names.b) || BLANK_READS;
      return {
        a: Assign.assign(namesA, leftTeam, slotRolesFor(heroRoles, s.a)),
        b: Assign.assign(namesB, rightTeam, slotRolesFor(heroRoles, s.b)),
      };
    });
  }

  // Step A (design doc §3.2): the MODE player_id assign() placed at each
  // VISUAL position, across every sample - that player's canonical slot.
  // Ties broken by player_id string order, so two runs over the same
  // samples never disagree (the same convention resolve.js's runnerUp uses).
  function canonicalSlotsFor(assigned, side) {
    var counts = [{}, {}, {}, {}, {}]; // counts[visualPos][playerId] = n
    assigned.forEach(function (a) {
      a[side].ids.forEach(function (id, pos) {
        if (!id) return;
        counts[pos][id] = (counts[pos][id] || 0) + 1;
      });
    });
    var canonicalSlotOf = {}; // playerId -> slot
    for (var pos = 0; pos < 5; pos++) {
      var best = null, bestN = -1;
      Object.keys(counts[pos]).sort().forEach(function (id) {
        if (counts[pos][id] > bestN) { bestN = counts[pos][id]; best = id; }
      });
      if (best !== null) canonicalSlotOf[best] = pos;
    }
    return canonicalSlotOf;
  }

  // Step B (design doc §3.2): re-key one sample's hero cells from visual
  // position into canonical slot order. A HIGH claim (assign() confidently
  // placed a player this sample, and that player has an established
  // canonical slot) always wins over a LOW claim (default: this position's
  // read belongs to its own slot index, unchanged) for the same target
  // slot. This is what makes an unclear/illegible name degrade to "no
  // change" rather than "hero data lost" - see the design doc's regression
  // note in §3.2.
  var ABSENT_CELL = { name: null, guid: 'ABSENT', score: null };
  function rekeySample(rawCells, sampleIds, canonicalSlotOf) {
    var high = [null, null, null, null, null];
    var low = [null, null, null, null, null];
    for (var pos = 0; pos < 5; pos++) {
      var id = sampleIds[pos];
      var target = id && canonicalSlotOf[id] !== undefined ? canonicalSlotOf[id] : null;
      if (target !== null) high[target] = rawCells[pos];
      else low[pos] = rawCells[pos];
    }
    var out = [];
    for (var slot = 0; slot < 5; slot++) {
      out.push(high[slot] || low[slot] || ABSENT_CELL);
    }
    return out;
  }

  // samples: [{ t, a: [cell x5], b: [cell x5], names: {a:[string x5], b:[string x5]} }]
  // feed: { hero_roles, lineups }. code: { match_id, game_no, t1, t2 }.
  function attributeFromSamples(samples, feed, code) {
    var heroRoles = feed.hero_roles || {};
    var t1 = playersFor(feed, code, 'a');
    var t2 = playersFor(feed, code, 'b');

    if (!samples.length) {
      return {
        correctedSamples: [],
        attribution: {
          a: { ids: BLANK_READS.map(function () { return null; }), conf: BLANK_READS.map(function () { return null; }) },
          b: { ids: BLANK_READS.map(function () { return null; }), conf: BLANK_READS.map(function () { return null; }) },
        },
        orientation: null,
      };
    }

    // Orientation: the mode of every sample's own confidentOrientation call
    // - still a once-per-map fact (a screen-side swap can't change mid-map),
    // just decided from every sample instead of one frame.
    var orientVotes = {};
    samples.forEach(function (s) {
      var namesA = (s.names && s.names.a) || BLANK_READS;
      var namesB = (s.names && s.names.b) || BLANK_READS;
      var o = Names.confidentOrientation(namesA, namesB, rosterNames(t1), rosterNames(t2));
      if (o) orientVotes[o] = (orientVotes[o] || 0) + 1;
    });
    var orient = null, orientN = -1;
    Object.keys(orientVotes).sort().forEach(function (o) {
      if (orientVotes[o] > orientN) { orientN = orientVotes[o]; orient = o; }
    });
    var swapped = orient === 'b';
    var leftTeam = swapped ? t2 : t1;
    var rightTeam = swapped ? t1 : t2;

    var assigned = perSampleAssign(samples, leftTeam, rightTeam, heroRoles);
    var canonicalSlotOf = { a: canonicalSlotsFor(assigned, 'a'), b: canonicalSlotsFor(assigned, 'b') };

    var correctedSamples = samples.map(function (s, i) {
      return {
        t: s.t,
        a: rekeySample(s.a, assigned[i].a.ids, canonicalSlotOf.a),
        b: rekeySample(s.b, assigned[i].b.ids, canonicalSlotOf.b),
      };
    });

    var attribution = { a: { ids: [null, null, null, null, null], conf: [null, null, null, null, null] },
                         b: { ids: [null, null, null, null, null], conf: [null, null, null, null, null] } };
    SIDES.forEach(function (side) {
      Object.keys(canonicalSlotOf[side]).forEach(function (id) {
        var slot = canonicalSlotOf[side][id];
        attribution[side].ids[slot] = id;
        attribution[side].conf[slot] = 'matched';
      });
    });

    return {
      correctedSamples: correctedSamples,
      attribution: attribution,
      orientation: orient === null ? null : (swapped ? 'swapped' : 'direct'),
    };
  }

  var Mod = {
    attributeFromSamples: attributeFromSamples,
    playersFor: playersFor, slotRolesFor: slotRolesFor, rosterNames: rosterNames,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayAttribute = Mod;
})(typeof self !== 'undefined' ? self : this);
