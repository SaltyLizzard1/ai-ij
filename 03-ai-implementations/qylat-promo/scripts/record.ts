/*
 * Drives the website with Playwright, records the screen, and writes a
 * timeline of everything the camera and captions need.
 *
 *   npm run record                       # full cut, portrait, live site
 *   npm run record:short                 # short cut (under a minute), portrait
 *   npm run record:wide                  # full cut, landscape
 *   npm run record:short:wide            # short cut, landscape
 *   BASE_URL=http://localhost:3000 npm run record   # records a local dev server
 *
 * Output, per variant:
 *   public/tour/<cut>-<format>/recording.mp4   (or .webm if no ffmpeg is available)
 *   public/tour/<cut>-<format>/timeline.json   camera moves, captions, url changes
 *   out/narration-script-<cut>.txt            the narration lines for a TTS pass
 */
import { chromium, type Locator, type Page } from 'playwright';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildTour } from '../tour';
import { variantId, type Box, type Cut, type Format, type Step, type Timeline, type TimelineEvent } from '../src/types';

const argv = process.argv.slice(2);
const CUT: Cut = argv.includes('--short') || process.env.CUT === 'short' ? 'short' : 'full';
const FORMAT: Format = argv.includes('--landscape') || process.env.FORMAT === 'landscape' ? 'landscape' : 'portrait';
const tour = buildTour(CUT, FORMAT);
const VARIANT = variantId(CUT, FORMAT);

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TOUR_DIR = path.join(ROOT, 'public', 'tour', VARIANT);
const NARRATION_DIR = path.join(ROOT, 'public', 'narration');
const OUT_DIR = path.join(ROOT, 'out');
const HEADLESS = process.env.HEADED !== '1';
// Capture above 1x so the zoomed shots stay sharp. A phone viewport needs 3x
// to fill 1080 px of width; the desktop viewport needs 2x. That makes the
// live browser window look huge on screen, so watch mode (HEADED=1) records
// at 1x unless RECORD_SCALE says otherwise.
const SCALE = Number(
  process.env.RECORD_SCALE ?? (!HEADLESS ? 1 : tour.format === 'portrait' ? 3 : 2),
);
const PORTRAIT = tour.format === 'portrait';

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
/** Recorder motions scaled by the tour's pace. Explicit `wait` values are not scaled. */
const paced = (ms: number) => Math.round(ms * tour.pace);

// A visible cursor. Screen recordings do not include the pointer, so this
// draws one that follows the mouse events Playwright dispatches, plus a
// gold ripple on click. Injected before any page script runs.
const ARROW_SVG =
  '<svg viewBox="0 0 26 34" width="26" height="34"><path d="M3 2 L3 26 L9.5 20.5 L13.5 30 L18 28 L14 18.5 L22 18.5 Z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
const DOT_SVG =
  '<svg viewBox="0 0 26 34" width="26" height="34"><circle cx="13" cy="13" r="11" fill="rgba(232,200,74,0.55)" stroke="rgba(139,105,20,0.9)" stroke-width="2"/></svg>';

const CURSOR_SCRIPT = `(() => {
  if (window.__tourCursor) return;
  window.__tourCursor = true;
  const PORTRAIT = ${PORTRAIT};
  const install = () => {
    const style = document.createElement('style');
    style.textContent = 'nextjs-portal{display:none!important}@keyframes __tourRipple{from{transform:translate(-50%,-50%) scale(.2);opacity:.9}to{transform:translate(-50%,-50%) scale(1);opacity:0}}';
    document.documentElement.appendChild(style);
    const c = document.createElement('div');
    c.id = '__tour_cursor';
    c.style.cssText = 'position:fixed;left:-100px;top:-100px;width:26px;height:34px;pointer-events:none;z-index:2147483647;filter:drop-shadow(0 2px 3px rgba(0,0,0,.5));opacity:0;transition:opacity .25s';
    c.innerHTML = PORTRAIT ? '${DOT_SVG}' : '${ARROW_SVG}';
    document.documentElement.appendChild(c);
    // On the phone layout the dot stands in for a fingertip, so it hides
    // when nothing is happening. The desktop arrow stays put like a real one.
    let idle = null;
    document.addEventListener('mousemove', (e) => {
      c.style.left = (e.clientX - (PORTRAIT ? 13 : 3)) + 'px';
      c.style.top = (e.clientY - (PORTRAIT ? 13 : 2)) + 'px';
      c.style.opacity = '1';
      if (PORTRAIT) {
        if (idle) clearTimeout(idle);
        idle = setTimeout(() => { c.style.opacity = '0'; }, 900);
      }
    }, true);
    document.addEventListener('mousedown', (e) => {
      const r = document.createElement('div');
      r.style.cssText = 'position:fixed;width:56px;height:56px;border-radius:50%;pointer-events:none;z-index:2147483646;background:rgba(232,200,74,.55);border:2px solid rgba(139,105,20,.9);animation:__tourRipple .5s ease-out forwards;left:' + e.clientX + 'px;top:' + e.clientY + 'px';
      document.documentElement.appendChild(r);
      setTimeout(() => r.remove(), 600);
    }, true);
  };
  if (document.documentElement) install(); else document.addEventListener('DOMContentLoaded', install);
})();`;

class Recorder {
  events: TimelineEvent[] = [];
  private t0 = 0;
  private cursor = { x: 200, y: 200 };

  constructor(private page: Page, private base: URL) {}

  start() {
    this.t0 = Date.now();
  }
  now() {
    return Date.now() - this.t0;
  }
  push(e: TimelineEvent) {
    this.events.push(e);
  }

  async locate(selector: string, timeout = 15000): Promise<Locator> {
    const loc = this.page.locator(selector).first();
    await loc.waitFor({ state: 'visible', timeout });
    return loc;
  }

  /** Scroll so the element sits in the middle of the viewport, smoothly. */
  async scrollIntoView(loc: Locator) {
    const moved = await loc.evaluate((el) => {
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight;
      if (r.top >= 96 && r.bottom <= vh - 48) return false;
      const target = window.scrollY + r.top - vh / 2 + r.height / 2;
      window.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
      return true;
    });
    if (moved) await sleep(paced(900));
  }

  async box(loc: Locator): Promise<Box> {
    const b = await loc.boundingBox();
    if (!b) throw new Error('Element has no bounding box');
    return { x: b.x, y: b.y, w: b.width, h: b.height };
  }

  /** Eased cursor motion so it reads as a hand, not a teleport. */
  async moveTo(x: number, y: number, ms = paced(480)) {
    const from = { ...this.cursor };
    const steps = Math.max(8, Math.round(ms / 16));
    for (let i = 1; i <= steps; i++) {
      const p = i / steps;
      const e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      await this.page.mouse.move(from.x + (x - from.x) * e, from.y + (y - from.y) * e);
      await sleep(ms / steps);
    }
    this.cursor = { x, y };
  }

  /** After a full navigation the injected cursor starts hidden. Nudge it. */
  async reshowCursor() {
    await this.page.mouse.move(this.cursor.x + 1, this.cursor.y);
    await this.page.mouse.move(this.cursor.x, this.cursor.y);
  }

  zoom(box: Box, level?: number) {
    this.push({ t: this.now(), type: 'zoom', box, level });
  }

  async run(step: Step) {
    const wait = 'wait' in step && step.wait !== undefined ? step.wait : 600;
    switch (step.action) {
      case 'goto': {
        await this.page.goto(new URL(step.path, this.base).toString(), { waitUntil: 'load' });
        await this.reshowCursor();
        await sleep(wait);
        return;
      }
      case 'wait':
        await sleep(step.ms);
        return;
      case 'zoomOut':
        this.push({ t: this.now(), type: 'zoomOut' });
        await sleep(wait);
        return;
      case 'zoom': {
        const loc = await this.locate(step.selector);
        await this.scrollIntoView(loc);
        this.zoom(await this.box(loc), step.level);
        await sleep(wait);
        return;
      }
      case 'scrollTo': {
        const loc = await this.locate(step.selector);
        await this.scrollIntoView(loc);
        if (step.zoom !== false) this.zoom(await this.box(loc), step.zoom);
        await sleep(wait);
        return;
      }
      case 'click':
      case 'type': {
        let loc: Locator;
        try {
          loc = await this.locate(step.selector);
        } catch (err) {
          if (step.action === 'click' && step.optional) {
            console.warn(`  skip (optional, not found): ${step.selector}`);
            return;
          }
          throw err;
        }
        await this.scrollIntoView(loc);
        const b = await this.box(loc);
        await this.moveTo(b.x + b.w / 2, b.y + b.h / 2);
        if (step.zoom !== false) this.zoom(b, step.zoom);
        await sleep(paced(160));
        await this.page.mouse.down();
        await sleep(90);
        await this.page.mouse.up();
        if (step.action === 'type') {
          await sleep(paced(250));
          await this.page.keyboard.type(step.text, { delay: paced(95) });
        }
        await sleep(wait);
        return;
      }
    }
  }
}

/** Duration in ms as ffmpeg reports it, or null if it cannot be read. */
function probeDurationMs(ffmpeg: string[], file: string): number | null {
  const r = spawnSync(ffmpeg[0], [...ffmpeg.slice(1), '-i', file, '-f', 'null', '-'], { encoding: 'utf8' });
  const m = /Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)/.exec(r.stderr ?? '');
  if (!m) return null;
  return Math.round((Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3])) * 1000);
}

function findFfmpeg(): string[] | null {
  if (spawnSync('ffmpeg', ['-version'], { stdio: 'ignore' }).status === 0) return ['ffmpeg'];
  // Remotion ships its own ffmpeg build.
  const remotion = path.join(ROOT, 'node_modules', '.bin', 'remotion');
  if (fs.existsSync(remotion) && spawnSync(remotion, ['ffmpeg', '-version'], { stdio: 'ignore' }).status === 0) {
    return [remotion, 'ffmpeg'];
  }
  return null;
}

async function main() {
  fs.mkdirSync(TOUR_DIR, { recursive: true });
  fs.mkdirSync(NARRATION_DIR, { recursive: true });
  fs.mkdirSync(OUT_DIR, { recursive: true });
  for (const f of fs.readdirSync(TOUR_DIR)) fs.rmSync(path.join(TOUR_DIR, f));

  const base = new URL(tour.baseUrl);
  console.log(`Recording ${base.origin}: ${VARIANT} at ${tour.viewport.width}x${tour.viewport.height} (${SCALE}x)`);
  if (!HEADLESS) {
    console.log('Watch mode: the browser window on screen is the capture, not the final video.');
    console.log('Keep that window visible and uncovered until it closes, or the footage goes grey.');
    console.log('The video is what `npm run render` writes to out/qylat-promo.mp4.');
    if (SCALE === 1) console.log('Recording at 1x for a normal-sized window. Run without HEADED for the sharp version.');
  }

  // Playwright only ever scales a recording down, so a 2x capture has to come
  // from Chromium itself rendering at 2x. The context's deviceScaleFactor
  // alone is not enough for the screencast.
  const browser = await chromium.launch({
    headless: HEADLESS,
    executablePath: process.env.PW_CHROMIUM || undefined,
    args: [
      `--force-device-scale-factor=${SCALE}`,
      // Chromium stops painting a tab it believes is hidden (window covered,
      // minimised, or off screen), and the recording turns grey for that
      // stretch. Keep rendering regardless.
      '--disable-backgrounding-occluded-windows',
      '--disable-renderer-backgrounding',
      '--disable-background-timer-throttling',
    ],
  });
  const context = await browser.newContext({
    viewport: tour.viewport,
    deviceScaleFactor: SCALE,
    recordVideo: {
      dir: TOUR_DIR,
      size: { width: tour.viewport.width * SCALE, height: tour.viewport.height * SCALE },
    },
    reducedMotion: 'no-preference',
    colorScheme: 'light',
  });
  await context.addInitScript(CURSOR_SCRIPT);

  const rec = new Recorder(await context.newPage(), base);
  rec.start();
  const page = rec['page'];
  page.setDefaultTimeout(15000);
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame()) return;
    const u = new URL(frame.url());
    if (u.origin === base.origin) rec.push({ t: rec.now(), type: 'url', path: u.pathname + u.hash });
  });

  // The intro card covers this. Give the first page time to load behind it.
  await page.goto(base.toString(), { waitUntil: 'load' });
  await sleep(Math.max(0, tour.introMs - 800));

  for (const scene of tour.scenes) {
    console.log(`Scene: ${scene.id}`);
    rec.push({
      t: rec.now(),
      type: 'scene',
      id: scene.id,
      eyebrow: scene.eyebrow,
      title: scene.title,
      subtitle: scene.subtitle,
      narration: scene.narration,
    });
    for (const step of scene.steps) {
      const label = 'selector' in step ? step.selector : 'path' in step ? step.path : '';
      console.log(`  ${step.action} ${label}`);
      try {
        await rec.run(step);
      } catch (err) {
        console.error(`  FAILED in scene "${scene.id}" on step ${step.action} ${label}`);
        throw err;
      }
    }
  }

  await sleep(tour.outroMs);
  const wallMs = rec.now();
  const video = page.video();
  await context.close();
  await browser.close();
  if (!video) throw new Error('No video was recorded');
  const webm = await video.path();

  let videoFile = path.basename(webm);
  let durationMs: number | null = null;
  const ffmpeg = findFfmpeg();
  if (ffmpeg) {
    const mp4 = path.join(TOUR_DIR, 'recording.mp4');
    console.log('Converting to mp4 ...');
    execFileSync(
      ffmpeg[0],
      [...ffmpeg.slice(1), '-y', '-i', webm, '-c:v', 'libx264', '-preset', 'medium', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-r', '60', '-movflags', '+faststart', mp4],
      { stdio: 'inherit' },
    );
    fs.rmSync(webm);
    videoFile = 'recording.mp4';
    durationMs = probeDurationMs(ffmpeg, mp4);
  } else {
    console.warn('ffmpeg not found; keeping the .webm. Remotion can read it, but mp4 seeks faster.');
    fs.renameSync(webm, path.join(TOUR_DIR, 'recording.webm'));
    videoFile = 'recording.webm';
  }

  const narration: Record<string, string> = {};
  for (const scene of tour.scenes) {
    for (const ext of ['mp3', 'wav', 'm4a']) {
      if (fs.existsSync(path.join(NARRATION_DIR, `${scene.id}.${ext}`))) {
        narration[scene.id] = `narration/${scene.id}.${ext}`;
        break;
      }
    }
  }

  // Optional background bed: drop an mp3 at public/music.mp3.
  const music = fs.existsSync(path.join(ROOT, 'public', 'music.mp3')) ? 'music.mp3' : undefined;

  const timeline: Timeline = {
    video: `tour/${VARIANT}/${videoFile}`,
    cut: tour.cut,
    music,
    host: base.host,
    format: tour.format,
    viewport: tour.viewport,
    wallMs,
    // Falls back to wall-clock time when ffmpeg is missing; captions may then
    // sit a few hundred ms late. Nudge with syncOffsetMs.
    durationMs: durationMs ?? wallMs,
    introMs: tour.introMs,
    outroMs: tour.outroMs,
    syncOffsetMs: 0,
    narration,
    events: rec.events,
  };
  fs.writeFileSync(path.join(TOUR_DIR, 'timeline.json'), JSON.stringify(timeline, null, 2));

  const script = tour.scenes
    .filter((s) => s.narration)
    .map((s) => `[${s.id}]\n${s.narration}\n`)
    .join('\n');
  fs.writeFileSync(path.join(OUT_DIR, `narration-script-${tour.cut}.txt`), script);

  console.log(`\nDone. ${rec.events.length} events, ${(wallMs / 1000).toFixed(1)}s of footage.`);
  console.log(`  public/tour/${VARIANT}/${videoFile}\n  public/tour/${VARIANT}/timeline.json\n  out/narration-script-${tour.cut}.txt`);
  const renderScript = `render${CUT === 'short' ? ':short' : ''}${FORMAT === 'landscape' ? ':wide' : ''}`;
  console.log(`\nNext: npm run studio   (preview, pick "${VARIANT}")   or   npm run ${renderScript}   (mp4)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
