// Renders tools/og_image.html to docs/og.png (1200x630, the link-embed card).
//   node tools/shoot_og.js
// Serves the repo root over http so the real ../docs/fonts/*.woff2 load (a
// file:// run silently falls back to system fonts and the wordmark comes out
// wrong). Needs Playwright's Firefox: npx playwright install firefox
const { firefox } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'docs', 'og.png');
const TYPES = { '.html': 'text/html; charset=utf-8', '.woff2': 'font/woff2',
  '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png' };

const server = http.createServer((req, res) => {
  const file = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    res.writeHead(404); res.end('not found'); return;
  }
  res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});

(async () => {
  await new Promise(r => server.listen(0, r));
  const port = server.address().port;
  const browser = await firefox.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 } });
  await page.goto(`http://localhost:${port}/tools/og_image.html`, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);   // don't shoot mid-swap
  await page.screenshot({ path: OUT, clip: { x: 0, y: 0, width: 1200, height: 630 } });
  await browser.close();
  server.close();
  console.log('wrote', OUT, fs.statSync(OUT).size, 'bytes');
})();
