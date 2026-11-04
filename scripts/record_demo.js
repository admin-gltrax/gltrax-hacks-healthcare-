// Record the demo video's screen clips, one per beat of docs/DEMO-PITCH.md.
//
//   BASE_URL=http://localhost:8000 node scripts/record_demo.js [out_dir] [clip names...]
//
// Writes out_dir/clipNN_*.mp4 (1280x800, 30 fps, H.264), stills (still_*.png), and
// out_dir/clips.json with each clip's length and timed marks ("clicked Start" at 4.2 s)
// for lining up the voiceover (docs/VOICEOVER.md). Needs Playwright and ffmpeg.
//
// clip04 runs a live prior-auth appeal (about 2 minutes of Meta model calls) against
// whatever server BASE_URL points at. Everything else is free: the swarm clip uses the
// recorded replay, never a live swarm. All data on screen is fictional.
const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const BASE = (process.env.BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const OUT = path.resolve(process.argv[2] || 'demo-clips');
const ONLY = process.argv.slice(3);
const W = 1280, H = 800;

// Playwright's video has no mouse pointer, so draw one that follows real mouse events.
const CURSOR = `(() => {
  const add = () => {
    if (document.getElementById('__cur')) return;
    const c = document.createElement('div'); c.id = '__cur';
    c.style.cssText = 'position:fixed;left:-50px;top:-50px;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
      'background:rgba(20,20,20,.35);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);z-index:2147483647;pointer-events:none;transition:transform .12s';
    document.documentElement.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { c.style.transform = 'scale(.7)'; }, true);
    addEventListener('mouseup', () => { c.style.transform = ''; }, true);
  };
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', add); else add();
})();`;

const pause = (p, ms) => p.waitForTimeout(ms);
const pos = new WeakMap();

async function moveTo(page, loc, { ms = 700 } = {}) {
  const box = await loc.boundingBox();
  if (!box) return;
  const x = box.x + Math.min(box.width / 2, 120), y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps: Math.max(8, Math.round(ms / 16)) });
  pos.set(page, { x, y });
}

// Eased scroll so the camera glides instead of jumping.
async function glide(page, to, ms = 1200) {
  await page.evaluate(([to, ms]) => new Promise(done => {
    const from = scrollY, d = to - from, t0 = performance.now();
    const step = t => {
      const k = Math.min(1, (t - t0) / ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      scrollTo(0, from + d * e); k < 1 ? requestAnimationFrame(step) : done();
    };
    requestAnimationFrame(step);
  }), [to, ms]);
}

async function show(page, loc, { where = 0.35, ms = 1200 } = {}) {
  await loc.waitFor({ state: 'visible' });
  const y = await loc.evaluate((el, where) => el.getBoundingClientRect().top + scrollY - innerHeight * where, where);
  await glide(page, Math.max(0, y), ms);
}

async function tap(page, loc, opts = {}) {
  await show(page, loc, opts);
  await moveTo(page, loc);
  await pause(page, opts.hover ?? 450);
  await loc.click();
}

async function openDemo(page) {
  await page.goto(BASE + '/');
  await page.getByText(/explore a demo patient/i).first().click();
  await page.getByText('What should PJ do?').first().waitFor();
  await pause(page, 800);
}

const results = {};

async function clip(browser, name, fn) {
  if (ONLY.length && !ONLY.some(o => name.startsWith(o))) return;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'clip-'));
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: tmp, size: { width: W, height: H } } });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const t0 = Date.now();
  let start = 0;
  const marks = [];
  const api = {
    ready: () => { start = (Date.now() - t0) / 1000; },          // everything before this is trimmed
    mark: label => marks.push({ t: +((Date.now() - t0) / 1000 - start).toFixed(1), label }),
    still: async file => page.screenshot({ path: path.join(OUT, file) }),
    note: {},
  };
  process.stdout.write(`recording ${name} ... `);
  try {
    await fn(page, api);
  } catch (e) {
    api.note.error = String(e).split('\n')[0];
    await page.screenshot({ path: path.join(OUT, name + '_error.png') }).catch(() => {});
  }
  const video = page.video();
  await ctx.close();
  const raw = await video.path();
  const out = path.join(OUT, name + '.mp4');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-ss', String(start + 0.15), '-i', raw,
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-r', '30', '-an', out]);
  const len = +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', out]).toString().trim();
  fs.rmSync(tmp, { recursive: true, force: true });
  results[name] = { file: name + '.mp4', seconds: +len.toFixed(1), marks, ...api.note };
  console.log(`${len.toFixed(1)} s${api.note.error ? '  ERROR: ' + api.note.error : ''}`);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();

  await clip(browser, 'clip01_problem', async (p, c) => {
    await p.goto(BASE + '/'); await p.getByText(/explore a demo patient/i).first().waitFor(); await pause(p, 600);
    c.ready(); c.mark('welcome page');
    await pause(p, 2500);
    await moveTo(p, p.locator('img').nth(1), { ms: 1500 }); c.mark('hover PJ');
    await pause(p, 3500);
    await glide(p, 650, 3000); c.mark('scrolled to what PJ does');
    await pause(p, 4000);
    await glide(p, 0, 2500); c.mark('back to top');
    await pause(p, 3500);
  });

  await clip(browser, 'clip02_product', async (p, c) => {
    await p.goto(BASE + '/'); await p.getByText(/explore a demo patient/i).first().waitFor(); await pause(p, 600);
    c.ready();
    await pause(p, 1200);
    await tap(p, p.getByText(/explore a demo patient/i).first(), { hover: 700 }); c.mark('clicked explore a demo patient');
    await p.getByText('What should PJ do?').first().waitFor();
    await pause(p, 300);
    await glide(p, 0, 400);
    await pause(p, 1500); c.mark('home: What should PJ do?');
    await c.still('still_home.png');
    for (const t of [/^Find a doctor who really takes/, /^Have PJ call your doctor/, /^Find benefits you/]) {
      await moveTo(p, p.getByRole('button', { name: t }).first(), { ms: 900 }); await pause(p, 1400);
    }
    c.mark('hovered action cards');
    await pause(p, 2000);
  });

  await clip(browser, 'clip03_mom', async (p, c) => {
    await openDemo(p); await glide(p, 0, 300);
    c.ready();
    await pause(p, 1000);
    await tap(p, p.getByRole('button', { name: /Rosa/ }).first(), { hover: 600 }); c.mark('clicked Rosa');
    const banner = p.getByText(/healthcare power of attorney for Rosa/).first();
    await banner.waitFor(); await pause(p, 800);
    await moveTo(p, banner, { ms: 900 }); c.mark('power of attorney banner');
    await pause(p, 2800);
    await tap(p, p.getByRole('button', { name: /^Find benefits Rosa/ }).first(), { hover: 700 }); c.mark('clicked find benefits');
    await pause(p, 2000);
    const rides = p.locator('.sup').filter({ hasText: /Free rides/ }).first();
    await show(p, rides, { where: 0.45, ms: 1800 }); c.mark('rides benefit');
    await pause(p, 1500);
    await tap(p, rides.getByRole('button', { name: 'Do it, PJ' }), { where: 0.45, hover: 800 }); c.mark('clicked Do it, PJ');
    await pause(p, 3500);
  });

  await clip(browser, 'clip04_appeal', async (p, c) => {
    await openDemo(p);
    await p.getByRole('button', { name: /Rosa/ }).first().click();
    await p.getByText(/healthcare power of attorney for Rosa/).first().waitFor(); await glide(p, 0, 300); await pause(p, 600);
    c.ready();
    await pause(p, 800);
    await tap(p, p.getByRole('button', { name: /^Appeal a prior-authorization denial/ }).first(), { hover: 700 }); c.mark('clicked appeal');
    await pause(p, 1500);
    await tap(p, p.getByText('Use the sample (fictional)').first(), { hover: 600 }); c.mark('used sample denial letter');
    await pause(p, 1500);
    await tap(p, p.getByRole('button', { name: /^Start/ }).first(), { hover: 600 }); c.mark('clicked Start');
    const card = p.locator('#wfs article.wf').filter({ hasText: /denial letter/ }).filter({ hasNotText: /signed by/ }).first();
    await card.waitFor({ timeout: 30000 });
    await show(p, card, { where: 0.08, ms: 1500 });
    // Follow the crew while it works: keep the live call or the running step in view.
    const t = Date.now();
    let sawCall = false;
    while (Date.now() - t < 300000) {
      if (await card.getByText('Needs a signature').count()) break;
      const live = card.locator('details.call[open]').filter({ hasText: /On the phone with/ });
      if (await live.count()) {
        if (!sawCall) { c.mark('live call streaming'); sawCall = true; }
        await show(p, live.locator('.transcript p').last(), { where: 0.7, ms: 700 });
      }
      await pause(p, 1500);
    }
    c.mark('crew finished: needs a signature');
    await show(p, card, { where: 0.08, ms: 1500 }); await pause(p, 3000);
    const open = async (re, label, hold) => {
      const s = card.locator('summary').filter({ hasText: re }).first();
      if (!(await s.count())) { c.note['missing_' + label] = true; return; }
      await tap(p, s, { where: 0.15, hover: 500 }); c.mark(label);
      await pause(p, 800);
      const body = s.locator('xpath=..');
      const h = await body.evaluate(el => el.getBoundingClientRect().height);
      if (h > 600) { await glide(p, await p.evaluate(() => scrollY) + Math.min(h - 500, 900), 2500); }
      await pause(p, hold);
    };
    await open(/Call to /, 'call transcript', 4500);
    await open(/The plan's rules/, "plan's rules answered", 3500);
    await open(/Stress test/, 'stress test', 4500);
    await open(/Guardrails/, 'guardrails', 3500);
    const sig = card.locator('input[placeholder$="to sign"]');
    await show(p, sig, { where: 0.6, ms: 1500 });
    const name = (await sig.getAttribute('placeholder')).replace(/^Type /, '').replace(/ to sign$/, '');
    await moveTo(p, sig); await sig.click(); await pause(p, 400);
    await sig.pressSequentially(name, { delay: 110 }); c.mark('typed signature');
    await pause(p, 800);
    await tap(p, card.getByRole('button', { name: 'Sign and send' }), { where: 0.6, hover: 700 }); c.mark('signed and sent');
    await pause(p, 2500);
    await show(p, p.locator('#wfs article.wf').filter({ hasText: /denial letter/ }).first(), { where: 0.08, ms: 1200 });
    await pause(p, 2500);
    await c.still('still_appeal_done.png');
  });

  await clip(browser, 'clip05_gym', async (p, c) => {
    await p.goto(BASE + '/gym'); await p.getByText('Call gym').first().waitFor(); await pause(p, 1000);
    c.ready(); c.mark('call gym tiles');
    await c.still('still_gym.png');
    await moveTo(p, p.getByText('600', { exact: true }).first(), { ms: 900 }); await pause(p, 1500);
    await moveTo(p, p.getByText('100%', { exact: true }).first(), { ms: 700 }); await pause(p, 1800);
    const sel = p.locator('select').first();
    await show(p, sel, { where: 0.12, ms: 1800 }); await moveTo(p, sel); await pause(p, 700);
    const opt = (await sel.locator('option').allInnerTexts()).find(o => /fake verification/i.test(o));
    if (opt) await sel.selectOption({ label: opt });
    c.mark('listen in: fake verification');
    await pause(p, 7000);
    await show(p, p.getByText('Stress test: the insurer tries', { exact: false }).first(), { where: 0.1, ms: 2000 }); c.mark('stress test results');
    await pause(p, 3500);
    await show(p, p.getByText('Cross-family judges').first(), { where: 0.1, ms: 2000 }); c.mark('judges kappa');
    await pause(p, 3500);
    await show(p, p.getByText('Reader eval').first(), { where: 0.1, ms: 2000 }); c.mark('reader eval');
    await pause(p, 3500);
  });

  await clip(browser, 'clip06_swarm', async (p, c) => {
    await p.goto(BASE + '/swarm'); await p.getByText('Replay recorded run').first().waitFor(); await pause(p, 800);
    c.ready();
    await pause(p, 1200);
    await tap(p, p.getByRole('button', { name: 'Replay recorded run' }), { hover: 700 }); c.mark('clicked replay');
    const dir = p.getByText(/Real directory search/i).last();
    await dir.waitFor({ timeout: 15000 }); await pause(p, 500);
    await moveTo(p, dir, { ms: 900 }); c.mark('directory step: real data');
    await pause(p, 3500);
    await p.mouse.move(450, 450, { steps: 40 }); c.mark('15 calls at once');
    await p.waitForFunction(() => /swarm_finished|Approve this slot/.test(document.body.innerText) &&
      !/No held offers yet/.test(document.body.innerText) && /Calls scored\s*15/.test(document.body.innerText), null, { timeout: 120000 });
    c.mark('swarm finished: best slot held');
    const best = p.getByText(/Best held offer/i).first();
    await moveTo(p, best, { ms: 900 });
    await pause(p, 4000);
    await c.still('still_swarm_best.png');
  });

  await clip(browser, 'clip07_close', async (p, c) => {
    await openDemo(p); await glide(p, 0, 300);
    c.ready(); c.mark('action menu');
    await pause(p, 1500);
    await glide(p, 700, 4000); await pause(p, 1500);
    await glide(p, 1300, 3000); c.mark('crew jobs');
    await pause(p, 2000);
    await glide(p, 0, 3000);
    await moveTo(p, p.locator('img').nth(1), { ms: 1200 }); c.mark('PJ');
    await pause(p, 4000);
  });

  if (!ONLY.length || ONLY.includes('still_phone')) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true });
    const p = await ctx.newPage();
    await openDemo(p); await p.evaluate(() => scrollTo(0, 0)); await pause(p, 600);
    await p.screenshot({ path: path.join(OUT, 'still_phone.png') });
    await ctx.close();
  }

  await browser.close();
  // Merge with earlier runs so re-recording one clip keeps the others' timings.
  const jf = path.join(OUT, 'clips.json');
  let prev = {};
  try { prev = JSON.parse(fs.readFileSync(jf, 'utf8')).clips || {}; } catch (e) { /* first run */ }
  fs.writeFileSync(jf, JSON.stringify({ base_url: BASE, recorded_at: new Date().toISOString(), clips: { ...prev, ...results } }, null, 2));
  console.log('wrote', OUT);
})();
