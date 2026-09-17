import { Config } from '@remotion/cli/config';

Config.setVideoImageFormat('jpeg');
Config.setOverwriteOutput(true);
// The recording is 1440x900 CSS px captured at 2x, so the zoomed-in shots
// stay sharp. JPEG quality 90 keeps the gold gradients clean.
Config.setJpegQuality(90);

// Remotion downloads its own headless Chrome on first render. On machines
// where that is blocked, point it at an existing Chromium binary instead:
//   BROWSER_EXECUTABLE=/path/to/chrome npm run render
if (process.env.BROWSER_EXECUTABLE) {
  Config.setBrowserExecutable(process.env.BROWSER_EXECUTABLE);
}
