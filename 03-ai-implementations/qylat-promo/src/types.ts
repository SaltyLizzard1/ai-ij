// Shared between the recorder (scripts/record.ts) and the Remotion
// composition (src/*). The recorder writes public/tour/timeline.json in
// the Timeline shape; the composition reads it back.

export type Step =
  /** Full page navigation. `path` is joined onto the tour's baseUrl. */
  | { action: 'goto'; path: string; wait?: number }
  /** Move the cursor to the element, zoom the camera on it (unless zoom is false), click. */
  | { action: 'click'; selector: string; zoom?: number | false; wait?: number; optional?: boolean }
  /** Click the field, then type the text one key at a time. */
  | { action: 'type'; selector: string; text: string; zoom?: number | false; wait?: number }
  /** Smooth-scroll the element into view, optionally zooming on it. */
  | { action: 'scrollTo'; selector: string; zoom?: number | false; wait?: number }
  /** Zoom the camera on an element without touching it. */
  | { action: 'zoom'; selector: string; level?: number; wait?: number }
  /** Return the camera to the full browser window. */
  | { action: 'zoomOut'; wait?: number }
  /** Hold on the current view. */
  | { action: 'wait'; ms: number };

export interface Scene {
  /** Used for the caption id and the optional narration file public/narration/<id>.mp3 */
  id: string;
  /** Small line above the title. Defaults to the site host. */
  eyebrow?: string;
  title: string;
  subtitle?: string;
  /** Spoken line for the scene. Written to out/narration-script.txt for a TTS pass. */
  narration?: string;
  steps: Step[];
}

export interface Tour {
  baseUrl: string;
  viewport: { width: number; height: number };
  /** Title card at the start. The recorder also holds this long so the page can load behind it. */
  introMs: number;
  /** Closing card at the end. The recorder holds the last page for this long. */
  outroMs: number;
  scenes: Scene[];
}

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type TimelineEvent =
  | { t: number; type: 'scene'; id: string; eyebrow?: string; title: string; subtitle?: string; narration?: string }
  | { t: number; type: 'zoom'; box: Box; level?: number }
  | { t: number; type: 'zoomOut' }
  | { t: number; type: 'url'; path: string };

export interface Timeline {
  /** Path under public/, e.g. "tour/recording.mp4" */
  video: string;
  /** Optional background music under public/, e.g. "music.mp3" */
  music?: string;
  /** Host shown in the fake address bar */
  host: string;
  viewport: { width: number; height: number };
  /** Wall-clock milliseconds from page creation to context close. */
  wallMs: number;
  /** Length of the video file in ms, as measured by ffmpeg after recording. */
  durationMs: number;
  introMs: number;
  outroMs: number;
  /** Manual nudge in ms if captions land early or late. Positive delays them. */
  syncOffsetMs: number;
  /** Narration files that existed at record time, keyed by scene id. */
  narration: Record<string, string>;
  events: TimelineEvent[];
}
