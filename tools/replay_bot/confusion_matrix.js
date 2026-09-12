// tools/replay_bot/confusion_matrix.js
// Reusable diagnostic: pairwise cosine similarity across every stored ref in
// docs/capture/refs.json, per side. For each hero, reports how well its own
// refs agree with each other (self-consistency) versus how close the nearest
// different-hero ref is (nearest-wrong-hero margin). Loads the exact matcher
// via match.js so the templates are built identically to production (same
// centering/L2-normalisation), not a reimplementation.
//
// Run: node tools/replay_bot/confusion_matrix.js
'use strict';

var fs = require('fs');
var path = require('path');
var Match = require('./match.js');

var refsPath = path.join(__dirname, '../../docs/capture/refs.json');
var refsJson = JSON.parse(fs.readFileSync(refsPath, 'utf8'));

Match.make(refsJson);
var REFS = global.REFS;

function cos(a, b) {
  var dot = 0;
  for (var i = 0; i < a.c.length; i++) dot += a.c[i] * b.c[i];
  return dot / (a.norm * b.norm);
}

var bySide = { a: [], b: [] };
REFS.forEach(function (r) { bySide[r.v].push(r); });

var results = {};
['a', 'b'].forEach(function (side) {
  var refs = bySide[side];
  var heroRefs = {};
  refs.forEach(function (r) { (heroRefs[r.n] = heroRefs[r.n] || []).push(r); });

  results[side] = {};
  Object.keys(heroRefs).forEach(function (heroName) {
    var mine = heroRefs[heroName];
    var selfSims = [];
    for (var i = 0; i < mine.length; i++) {
      for (var j = i + 1; j < mine.length; j++) selfSims.push(cos(mine[i], mine[j]));
    }
    var selfMin = selfSims.length ? Math.min.apply(null, selfSims) : 1;

    var nearest = { score: -2, name: null };
    mine.forEach(function (mr) {
      refs.forEach(function (r) {
        if (r.n === heroName) return;
        var s = cos(mr, r);
        if (s > nearest.score) nearest = { score: s, name: r.n };
      });
    });

    results[side][heroName] = {
      refCount: mine.length,
      selfMin: selfMin,
      nearestWrongHero: nearest.name,
      nearestWrongScore: nearest.score,
      margin: selfMin - nearest.score,
    };
  });
});

fs.writeFileSync(
  path.join(__dirname, 'confusion_matrix.out.json'),
  JSON.stringify(results, null, 2)
);

if (require.main === module) {
  ['a', 'b'].forEach(function (side) {
    var rows = Object.keys(results[side]).map(function (hero) {
      return Object.assign({ hero: hero }, results[side][hero]);
    });
    rows.sort(function (x, y) { return x.margin - y.margin; });
    console.log('--- side ' + side + ': tightest margins (self-consistency minus nearest wrong hero) ---');
    rows.slice(0, 15).forEach(function (r) {
      console.log(
        r.hero.padEnd(14),
        'margin=' + r.margin.toFixed(3),
        ' selfMin=' + r.selfMin.toFixed(3),
        ' vs ' + r.nearestWrongHero + ' (' + r.nearestWrongScore.toFixed(3) + ')'
      );
    });
  });
}

module.exports = { results: results };
