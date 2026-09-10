const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const canvas = require('@napi-rs/canvas');
const RO = require('./review_out.js');
const calib = require('./calib.js');
const Corpus = require('./corpus.js');

const skip = Corpus.absent() || false;

function tmpdir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'reviewout-'));
}

// A frame drawn to the frozen resolution, so writeStrip has a real box to cut.
function blankFrame() {
  const f = calib.FROZEN.frame;
  const cv = canvas.createCanvas(f.w, f.h);
  const cx = cv.getContext('2d');
  cx.fillStyle = '#123'; cx.fillRect(0, 0, f.w, f.h);
  return cv;
}

const io = { loadImage: (p) => (typeof p === 'string' ? canvas.loadImage(p) : Promise.resolve(p)) };

const CODE = {
  code: 'ABC123', match_id: 'm1', game_no: 2, map: 'Busan', map_category: 'Control',
  team_a: 'Wasp', team_b: 'NewGens', t1: 't-a', t2: 't-b',
};

test('mapEntry writes one crop per round per side and points at them relatively', async () => {
  const dir = tmpdir();
  const frame = blankFrame();
  const got = {
    samples: [{ t: 100, framePath: frame }, { t: 500, framePath: frame }],
  };
  const resolved = [
    { round_no: 1, from_t: 0, to_t: 300, a: [], b: [], flags: [] },
    { round_no: 2, from_t: 400, to_t: 700, a: [], b: [], flags: [] },
  ];

  const entry = await RO.mapEntry(io, dir, CODE, resolved, null, got, calib);

  assert.deepStrictEqual(Object.keys(entry.frames).sort(), ['1', '2']);
  assert.strictEqual(entry.frames['1'].a, 'crops/ABC123-r1-a.png');
  assert.strictEqual(entry.frames['2'].b, 'crops/ABC123-r2-b.png');
  for (const rel of ['crops/ABC123-r1-a.png', 'crops/ABC123-r1-b.png',
                     'crops/ABC123-r2-a.png', 'crops/ABC123-r2-b.png']) {
    assert.ok(fs.existsSync(path.join(dir, rel)), rel + ' should exist');
  }
  assert.strictEqual(entry.status, 'unreviewed');
  assert.deepStrictEqual(entry.corrections, []);
  assert.strictEqual(entry.side_a_team, 'Wasp');

  fs.rmSync(dir, { recursive: true, force: true });
});

test('a round with no frame is skipped, not crashed on', async () => {
  const dir = tmpdir();
  const frame = blankFrame();
  const got = { samples: [{ t: 100, framePath: frame }] };   // nothing in round 2's window
  const resolved = [
    { round_no: 1, from_t: 0, to_t: 300, a: [], b: [], flags: [] },
    { round_no: 2, from_t: 400, to_t: 700, a: [], b: [], flags: ['round-unsampled'] },
  ];

  const entry = await RO.mapEntry(io, dir, CODE, resolved, null, got, calib);
  assert.deepStrictEqual(Object.keys(entry.frames), ['1']);

  fs.rmSync(dir, { recursive: true, force: true });
});

test('writeSession round-trips and carries the meta', () => {
  const dir = tmpdir();
  const p = path.join(dir, 'replay-bot-2026-09-10.review.json');
  RO.writeSession(p, [{ demo_code: 'X' }], { session: 'replay-bot-2026-09-10', feedBuilt: '2026-09-10T01:00:00Z' });

  const back = JSON.parse(fs.readFileSync(p, 'utf8'));
  assert.strictEqual(back.session, 'replay-bot-2026-09-10');
  assert.strictEqual(back.feed_built_at, '2026-09-10T01:00:00Z');
  assert.strictEqual(back.maps.length, 1);
  assert.ok(back.built_at);

  fs.rmSync(dir, { recursive: true, force: true });
});

// The strip is cut from the real portrait box, so on a real frame it should be
// the portraits - checked here only for size and non-emptiness; the eyeball
// check is contact_sheet.js's job.
test('writeStrip cuts a box-sized PNG from a real frame', { skip }, async () => {
  const dir = tmpdir();
  const img = await canvas.loadImage(Corpus.file('panel-open'));
  const dest = path.join(dir, 'strip.png');
  RO.writeStrip(img, calib.FROZEN.boxes.a, dest);

  const out = await canvas.loadImage(dest);
  assert.ok(Math.abs(out.width - Math.round(calib.FROZEN.boxes.a.w)) <= 1);
  assert.ok(out.height > calib.FROZEN.boxes.a.h);

  fs.rmSync(dir, { recursive: true, force: true });
});
