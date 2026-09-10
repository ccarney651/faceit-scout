// tools/replay_bot/review_out.js
// The session review artifact: what the local review page reads.
// See specs/2026-09-10-replay-bot-autonomous-scouting-design.md §3.
//
// run.js already writes the contribution (out/replay-bot-<date>.json). This
// writes a SECOND file beside it, out/replay-bot-<date>.review.json, plus one
// portrait-strip crop per round per side under out/<session>/crops/. The
// contribution is what uploads; this is what the operator looks at first.
//
// The crop is the frame's portrait band (calib.FROZEN.boxes) - portraits, name
// plates and health pips - cut from the frame the round's first sample was read
// off. A whole frame is ~4MB; a strip is a few KB, and it is all the review
// page needs to check a hero by eye.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');
  var canvas = require('@napi-rs/canvas');

  // A little vertical slack around the frozen box so a plate that drew a few
  // pixels low is still whole in the crop.
  var PAD_Y = 12;

  function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }

  // Cut one side's portrait band out of a frame and write it as a PNG.
  function writeStrip(img, box, dest) {
    var x = Math.max(0, Math.round(box.x));
    var y = Math.max(0, Math.round(box.y) - PAD_Y);
    var w = Math.min(img.width - x, Math.round(box.w));
    var h = Math.min(img.height - y, Math.round(box.h) + PAD_Y * 2);
    var cv = canvas.createCanvas(w, h);
    cv.getContext('2d').drawImage(img, x, y, w, h, 0, 0, w, h);
    fs.writeFileSync(dest, cv.toBuffer('image/png'));
  }

  // One map's review entry. Crops are written under <sessionDir>/crops/ and the
  // returned object points at them by a path relative to the review.json.
  //
  //   code        the queue entry (match_id, game_no, map, teams, ...)
  //   resolved    resolve.rounds() output for this map
  //   attribution attribute.attributeMap() result, or null
  //   got         captureMap() result (for the per-round first-sample frame)
  //   calib       calib.js
  async function mapEntry(io, sessionDir, code, resolved, attribution, got, calib) {
    var cropsDir = path.join(sessionDir, 'crops');
    ensureDir(cropsDir);

    var frames = {};
    for (var i = 0; i < resolved.length; i++) {
      var r = resolved[i];
      var first = (got.samples || []).find(function (s) {
        return s.t >= r.from_t && s.t <= r.to_t;
      });
      if (!first || !first.framePath) continue;
      var img = await io.loadImage(first.framePath);
      var pair = {};
      ['a', 'b'].forEach(function (side) {
        var name = code.code + '-r' + r.round_no + '-' + side + '.png';
        writeStrip(img, calib.FROZEN.boxes[side], path.join(cropsDir, name));
        pair[side] = 'crops/' + name;
      });
      frames[String(r.round_no)] = pair;
    }

    return {
      demo_code: code.code,
      match_id: code.match_id,
      game_no: code.game_no,
      map_name: code.map,
      map_category: code.map_category,
      side_a_team: code.team_a,
      side_b_team: code.team_b,
      side_a_team_id: code.t1,
      side_b_team_id: code.t2,
      rounds: resolved,
      attribution: attribution || null,
      frames: frames,
      corrections: [],
      status: 'unreviewed',
    };
  }

  // The whole artifact. Rewritten after every map, like the contribution, so a
  // run that dies late still leaves a reviewable session.
  function writeSession(reviewPath, maps, meta) {
    var body = {
      session: (meta && meta.session) || path.basename(reviewPath).replace(/\.review\.json$/, ''),
      built_at: new Date().toISOString(),
      feed_built_at: (meta && meta.feedBuilt) || null,
      maps: maps,
    };
    ensureDir(path.dirname(reviewPath));
    fs.writeFileSync(reviewPath, JSON.stringify(body, null, 2) + '\n', 'utf8');
  }

  var Mod = { PAD_Y: PAD_Y, writeStrip: writeStrip, mapEntry: mapEntry, writeSession: writeSession };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayReviewOut = Mod;
})(typeof self !== 'undefined' ? self : this);
