# QYLAT promo video

An automated walkthrough of quityourlifeandtravel.com. Playwright drives the
site (clicks the nav, answers quiz questions, types into the calculator) and
records the screen. Remotion then wraps that footage in a browser window,
adds Screen-Studio style camera zooms onto whatever was clicked, and layers
the captions, title card and call to action on top.

Nothing is timed by hand. The recorder measures every element it touches and
writes the camera moves and caption cues to `public/tour/timeline.json`.
Change the tour, re-record, re-render.

## Setup

```bash
cd 03-ai-implementations/qylat-promo
npm install
npx playwright install chromium
```

## Make the video

```bash
npm run record      # drives the live site, writes public/tour/recording.mp4 + timeline.json
npm run studio      # optional: scrub the result in the Remotion Studio
npm run render      # writes out/qylat-promo.mp4 (1920x1080, 60 fps)
```

`npm run video` runs record and render back to back.

## Edit the tour

Everything the video does is in `tour.ts`: the scene order, the on-screen
text, the narration line for each scene, and the steps the browser performs.
Step actions:

| action     | what it does                                                          |
|------------|-----------------------------------------------------------------------|
| `goto`     | full page navigation to `path`                                        |
| `click`    | move the cursor to `selector`, zoom the camera on it, click           |
| `type`     | click the field, then type `text` key by key                          |
| `scrollTo` | smooth-scroll `selector` into view, zoom on it                        |
| `zoom`     | zoom on `selector` without touching it (`level` overrides auto zoom)  |
| `zoomOut`  | return to the full browser window                                     |
| `wait`     | hold for `ms`                                                         |

`zoom` on click/type/scrollTo steps takes a number (camera scale, 1.15 to
2.4), `false` to skip the zoom, or nothing to let the camera pick a level
that fits the element.

Selectors are Playwright selectors. `text="Leap Calculator"` matches by text,
`button:has-text("Next")` by contained text, and `#idea-to-plan h2` by CSS.

## Narration and music

Each scene has a `narration` line. The recorder writes them all to
`out/narration-script.txt`. Record or generate the voiceover however you
like, then drop one file per scene at `public/narration/<scene id>.mp3`
(for example `public/narration/calculator.mp3`). The next `npm run record`
picks them up and Remotion plays each one at its scene's start.

A background bed goes at `public/music.mp3`. It loops at low volume under
everything.

## Options

| variable            | effect                                                      |
|---------------------|-------------------------------------------------------------|
| `BASE_URL`          | record a different origin, e.g. `http://localhost:3000`     |
| `HEADED=1`          | watch the browser while it records                          |
| `SUBMIT_QUIZ=1`     | actually submit the Discover Your Idea form (slow)          |
| `RECORD_SCALE`      | capture scale, default 2 (sharp zooms), 1 is faster         |
| `PW_CHROMIUM`       | path to a Chromium binary if Playwright cannot download one |
| `BROWSER_EXECUTABLE`| headless Chrome for Remotion if it cannot download one      |

If captions or zooms land a touch early or late against the footage, set
`syncOffsetMs` in `public/tour/timeline.json` (positive delays them) and
re-render. Re-recording resets it to 0.

## Layout

```
tour.ts               the storyboard: scenes, text, narration, browser steps
scripts/record.ts     Playwright recorder: cursor overlay, smooth scrolling, timeline
src/Root.tsx          registers the composition, sizes it to the recording
src/PromoVideo.tsx    browser window + camera + captions + narration + cards
src/camera.ts         zoom maths: element box -> camera target, spring between targets
src/BrowserWindow.tsx macOS-style frame with a live address bar
src/Caption.tsx       lower-third caption per scene
src/TitleCards.tsx    hook card and call-to-action overlay
src/theme.ts          brand colours and fonts, copied from the site
public/fonts/         Cormorant Garamond 700, same file the site ships
```

Site conventions the tour depends on: nav labels in `components/Header.tsx`,
section ids `discover-your-idea` and `idea-to-plan` on the homepage, the
`Spendable cash` placeholder in the calculator, and the quiz option text in
`lib/leapTest.ts`. If those change on the site, update the selectors here.
