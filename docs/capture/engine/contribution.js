// docs/capture/engine/contribution.js
// What leaves the browser when a scout presses Publish.
//
// IndexedDB keeps every map ever captured in this browser, across every season,
// and publish() sent all of them. On 2026-09-08 a publish of two Season 10
// matches carried 31 Season 9 playoff maps with it, and 25 reached the live site
// as season 10 coverage before anyone noticed. Re-sending an already-published
// map is deliberate (an operator may fix and re-publish one); sending another
// season's is not, and nothing between the browser and the site checked.
//
// THE FEED IS THE SEASON. A map can only be captured after picking its code out
// of data.json, so a match_id the feed no longer carries belongs to a season
// that has since rolled over. No date arithmetic, no season string to keep in
// step with the server - the same list the operator picked from is the test.
//
// This is the honest MESSAGE, not the enforcement: owdb/contribute.py refuses an
// out-of-season map server-side regardless of which client sent it, and a stale
// cached page cannot get around that.
//
// Works as a browser global (`window.OWDBContribution`) and as a CommonJS module
// for node:test / pytest.

(function (global) {
  'use strict';

  // splitBySeason(maps, codes) -> {send, held}
  //
  // `send` is everything the current feed still knows about; `held` is the rest,
  // which stays in IndexedDB unpublished so nothing is lost and a later season's
  // feed could still claim it.
  //
  // AN EMPTY FEED FILTERS NOTHING. A local checkout ships data.json with
  // `codes: []` (CI publishes the real one), and filtering against it would hold
  // back every map and look like a broken Publish button. Distinguishing "no
  // codes right now" from "no feed" is not this function's job - with nothing to
  // compare against, the honest answer is to send what it was given and let the
  // server decide.
  function splitBySeason(maps, codes) {
    var list = maps || [];
    var ids = Object.create(null), n = 0;
    (codes || []).forEach(function (c) {
      if (c && c.match_id && !ids[c.match_id]) { ids[c.match_id] = true; n++; }
    });
    if (!n) return { send: list.slice(), held: [] };
    var send = [], held = [];
    for (var i = 0; i < list.length; i++) {
      (ids[list[i] && list[i].match_id] ? send : held).push(list[i]);
    }
    return { send: send, held: held };
  }

  // How to say what was held back, or '' when nothing was. Phrased as a fact
  // about the maps rather than a warning about the tool: holding them back is
  // correct behaviour, and an operator who reads "31 maps were not sent" with no
  // reason will assume something broke.
  function heldNote(held) {
    var n = (held || []).length;
    if (!n) return '';
    return n + ' saved map' + (n === 1 ? '' : 's') + ' from an earlier season '
      + (n === 1 ? 'was' : 'were') + ' not sent — ' + (n === 1 ? 'it stays' : 'they stay')
      + ' in this browser.';
  }

  var Mod = { splitBySeason: splitBySeason, heldNote: heldNote };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBContribution = Mod;
})(typeof self !== 'undefined' ? self : this);
