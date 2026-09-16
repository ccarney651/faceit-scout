// tools/replay_bot/review/landing.js
// Which tab the page opens on: Run when there's a run in progress or
// nothing to review yet, Review when a run just produced something to look
// at. Extracted from page.html's bootstrap so it's unit-testable - the rest
// of the page's wiring is DOM plumbing, verified by hand per this project's
// "pytest/node --test cannot see through a real browser" limitation.
'use strict';
function landingView(status) {
  if (status && status.running) return 'run';
  if (status && status.hasReview) return 'review';
  return 'run';
}
module.exports = { landingView };
