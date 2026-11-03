// Render video/intro.html (the opening motion graphic) to an MP4, frame by frame.
//
//   node scripts/render_intro.js [out.mp4] [vo01_seconds]
//
// Output: 1280x800, 30 fps, H.264, silent; a drop-in replacement for clip01_problem.mp4.
// Pass the real length of vo01_problem (in seconds) to retime the cues to your voice.
// Each frame is rendered at 2x and scaled down, so edges stay crisp.
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const OUT = path.resolve(process.argv[2] || 'clip01_problem.mp4');
const DUR = process.argv[3];
const FPS = 30;

(async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'intro-'));
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
  const url = 'file://' + path.resolve(__dirname, '../video/intro.html') + '?render=1' + (DUR ? '&dur=' + DUR : '');
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  const font = await page.evaluate(() => document.fonts.check('800 40px "Plus Jakarta Sans"'));
  if (!font) console.warn('warning: Plus Jakarta Sans did not load; falling back to Inter/system fonts');
  const length = await page.evaluate(() => window.LENGTH);
  const frames = Math.round(length * FPS);
  for (let i = 0; i < frames; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    await page.screenshot({ path: path.join(dir, `f${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 95 });
    if (i % 90 === 0) process.stdout.write(`${(i / FPS).toFixed(0)}s `);
  }
  await browser.close();
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS), '-i', path.join(dir, 'f%05d.jpg'),
    '-vf', 'scale=1280:800:flags=lanczos', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '16', '-r', String(FPS), '-an', OUT]);
  fs.rmSync(dir, { recursive: true, force: true });
  console.log(`\nwrote ${OUT} (${length.toFixed(1)} s, ${frames} frames)`);
})();
