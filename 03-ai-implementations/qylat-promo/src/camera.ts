import { spring } from 'remotion';
import type { Box, Format } from './types';

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Where the browser window and its content sit inside the output frame. */
export interface Layout {
  format: Format;
  frame: { w: number; h: number };
  headerH: number;
  window: Rect;
  content: Rect;
  radius: number;
  /** Upper bound for automatic zoom levels. */
  maxAutoZoom: number;
}

export const FRAME_SIZE: Record<Format, { w: number; h: number }> = {
  landscape: { w: 1920, h: 1080 },
  portrait: { w: 1080, h: 1920 },
};

export function makeLayout(format: Format, viewport: { width: number; height: number }): Layout {
  const frame = FRAME_SIZE[format];
  if (format === 'landscape') {
    const headerH = 60;
    const contentW = 1440;
    const contentH = Math.round((contentW * viewport.height) / viewport.width);
    const win = { w: contentW, h: contentH + headerH };
    const x = Math.round((frame.w - win.w) / 2);
    const y = Math.round((frame.h - win.h) / 2);
    return {
      format,
      frame,
      headerH,
      window: { x, y, w: win.w, h: win.h },
      content: { x, y: y + headerH, w: contentW, h: contentH },
      radius: 18,
      maxAutoZoom: 1.6,
    };
  }
  // Portrait: a phone-shaped window with a slim address bar, nearly edge to edge.
  const margin = 30;
  const headerH = 84;
  const contentW = frame.w - margin * 2;
  const contentH = Math.round((contentW * viewport.height) / viewport.width);
  const win = { w: contentW, h: contentH + headerH };
  const y = Math.max(margin, Math.round((frame.h - win.h) / 2));
  return {
    format,
    frame,
    headerH,
    window: { x: margin, y, w: win.w, h: win.h },
    content: { x: margin, y: y + headerH, w: contentW, h: contentH },
    radius: 44,
    maxAutoZoom: 1.35,
  };
}

export interface Camera {
  scale: number;
  tx: number;
  ty: number;
}

export const BASE_CAMERA: Camera = { scale: 1, tx: 0, ty: 0 };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Camera that centres a page element. `box` is in CSS px of the recorded
 * viewport and is mapped onto the layout's content area.
 */
export function cameraForBox(
  box: Box,
  viewport: { width: number; height: number },
  level: number | undefined,
  layout: Layout,
): Camera {
  const { frame, content, window: win } = layout;
  const sx = content.w / viewport.width;
  const sy = content.h / viewport.height;
  const w = box.w * sx;
  const h = box.h * sy;
  const cx = content.x + (box.x + box.w / 2) * sx;
  const cy = content.y + (box.y + box.h / 2) * sy;

  // Auto level: fit the element with generous margin, within the layout's cap.
  const auto = Math.min(frame.w / (w * 1.9), frame.h / (h * 2.6));
  const scale = clamp(level ?? auto, 1.1, level === undefined ? layout.maxAutoZoom : 2.4);

  // With transform-origin at the frame centre C, a point p lands at
  // C + scale * (p - C) + t. Solve t so the element centre lands on C.
  const C = { x: frame.w / 2, y: frame.h / 2 };
  let tx = -scale * (cx - C.x);
  let ty = -scale * (cy - C.y);

  // Keep the browser window covering the frame while zoomed, when it can.
  const txMin = frame.w - (C.x + scale * (win.x + win.w - C.x));
  const txMax = -(C.x + scale * (win.x - C.x));
  const tyMin = frame.h - (C.y + scale * (win.y + win.h - C.y));
  const tyMax = -(C.y + scale * (win.y - C.y));
  if (txMin <= txMax) tx = clamp(tx, txMin, txMax);
  else tx = 0;
  if (tyMin <= tyMax) ty = clamp(ty, tyMin, tyMax);

  return { scale, tx, ty };
}

export interface CameraKey {
  frame: number;
  target: Camera;
}

const SPRING = { damping: 22, stiffness: 70, mass: 0.9, overshootClamping: true };

/**
 * Walk the keyframes in order, springing from wherever the camera was to
 * each new target. Overlapping moves blend instead of snapping.
 */
export function cameraAtFrame(keys: CameraKey[], frame: number, fps: number): Camera {
  let cam = { ...BASE_CAMERA };
  for (const k of keys) {
    if (frame < k.frame) break;
    const p = spring({ frame: frame - k.frame, fps, config: SPRING });
    cam = {
      scale: cam.scale + (k.target.scale - cam.scale) * p,
      tx: cam.tx + (k.target.tx - cam.tx) * p,
      ty: cam.ty + (k.target.ty - cam.ty) * p,
    };
  }
  return cam;
}
