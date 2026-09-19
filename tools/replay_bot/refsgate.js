// tools/replay_bot/refsgate.js
// Refuse a capture run whose reference library has not been swept.
//
// WHY THIS EXISTS. Three separate refs.json regressions reached live capture,
// and the worst of them - 2026-09-15, a rebuild without --profile 7 - reverted
// all 53 heroes to the live-spectate source and ran for ~20 hours before
// anyone noticed. None of them were visible: the file is one line of base64,
// so the diff says nothing, the unit tests pass, and the capture reports a
// confident hero for every slot. The only thing that has ever caught this
// class is match_accuracy_sweep.js, and it only runs when someone remembers.
//
// So: the sweep records WHICH library it passed on, and a run refuses to start
// against a library that record does not cover. The fingerprint is the whole
// mechanism - if refs.json has not changed, the sweep's verdict still holds and
// the gate costs nothing; if it has changed, the verdict is about a different
// file and the operator is told to re-sweep before spending a night.

const crypto = require('crypto');

// Everything that decides what a hero match means: the crop box the library
// was built against, and the descriptors themselves. Ref ORDER is not part of
// it - a rebuild that emits the same library in a different order is the same
// library - so entries are sorted before hashing. JSON-encoded rather than
// joined on a separator, so no field's contents can blur into the next.
function fingerprint(library) {
  const geometry = [
    library.w, library.h,
    library.left_fraction, library.top_fraction, library.right_fraction,
  ];
  const refs = (library.refs || [])
    .map((r) => JSON.stringify([r.n, r.v, r.d]))
    .sort();
  return crypto.createHash('sha256')
    .update(JSON.stringify([geometry, refs]))
    .digest('hex').slice(0, 16);
}

const SWEEP = 'node tools/replay_bot/match_accuracy_sweep.js';

// `record` is state/refs_gate.json as the sweep last wrote it, or null when no
// sweep has ever passed on this machine.
function check(library, record) {
  const current = fingerprint(library);
  if (!record || !record.fingerprint) {
    return {
      ok: false,
      fingerprint: current,
      reason: 'no reference-library sweep has ever passed here. Run ' + SWEEP +
        ' and let it finish before capturing.',
    };
  }
  if (record.fingerprint !== current) {
    return {
      ok: false,
      fingerprint: current,
      reason: 'refs.json has changed since the sweep passed (passed on ' +
        record.fingerprint + ', now ' + current + '). A capture run against an ' +
        'unswept library is how the 2026-09-15 regression got 20 hours of ' +
        'confident wrong heroes. Re-run ' + SWEEP + ' first.',
    };
  }
  return { ok: true, fingerprint: current, passedAt: record.passed_at };
}

module.exports = { fingerprint, check, SWEEP };
