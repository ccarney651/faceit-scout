const test = require('node:test');
const assert = require('node:assert');
const { landingView } = require('./landing.js');

test('lands on Run when a run is active', () => {
  assert.strictEqual(landingView({ running: true, hasReview: true }), 'run');
});

test('lands on Run when nothing to review and no run has happened', () => {
  assert.strictEqual(landingView({ running: false, hasReview: false }), 'run');
});

test('lands on Review when a run just finished and there is something to review', () => {
  assert.strictEqual(landingView({ running: false, hasReview: true, exitInfo: { code: 0 } }), 'review');
});
