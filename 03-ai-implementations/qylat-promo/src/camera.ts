import { spring } from 'remotion';
import type { Box } from './types';

// Frame and browser window geometry, all in output pixels.
export const FRAME = { w: 1920, h: 1080 };
export const HEADER_H = 60;
export const CONTENT = { w: 1440, h: 900 };
export const WINDOW = { w: CONTENT.w, h: CONTENT.h + HEADER_H };
export const WINDOW_POS = { x: (FRAME.w - WINDOW.w) / 2, y: (FRAME.h - WINDOW.h) / 2 };
export const CONTENT_POS = { x: WINDOW_POS.x, y: WINDOW_POS.y + HEADER_H };

export interface Camera {
  scale: number;
  tx: number;
  ty: number;
}

export const BASE_CAMERA: Camera = { scale: 1, tx: 0, ty: 0 };

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/**
 * Camera that centres a page element. `box` is in CSS px of the recorded
 * viewport; `viewport` is that viewport's size, so recordings at other sizes
 * still map onto the 1440x900 content area.
 */
export function cameraForBox(
  box: Box,
  viewport: { width: number; height: number },
  level?: number,
): Camera {
  const sx = CONTENT.w / viewport.width;
  const sy = CONTENT.h / viewport.height;
  const w = box.w * sx;
  const h = box.h * sy;
  const cx = CONTENT_POS.x + (box.x + box.w / 2) * sx;
  const cy = CONTENT_POS.y + (box.y + box.h / 2) * sy;

  // Auto level: fit the element with generous margin, never past 2.4x.
  const auto = Math.min(FRAME.w / (w * 1.9), FRAME.h / (h * 2.6));
  const scale = clamp(level ?? auto, 1.15, 2.4);

  // With transform-origin at the frame centre C, a point p lands at
  // C + scale * (p - C) + t. Solve t so the element centre lands on C.
  const C = { x: FRAME.w / 2, y: FRAME.h / 2 };
  let tx = -scale * (cx - C.x);
  let ty = -scale * (cy - C.y);

  // Keep the browser window covering the frame while zoomed, when it can.
  const left = WINDOW_POS.x;
  const right = WINDOW_POS.x + WINDOW.w;
  const top = WINDOW_POS.y;
  const bottom = WINDOW_POS.y + WINDOW.h;
  const txMin = FRAME.w - (C.x + scale * (right - C.x));
  const txMax = -(C.x + scale * (left - C.x));
  const tyMin = FRAME.h - (C.y + scale * (bottom - C.y));
  const tyMax = -(C.y + scale * (top - C.y));
  if (txMin <= txMax) tx = clamp(tx, txMin, txMax);
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
