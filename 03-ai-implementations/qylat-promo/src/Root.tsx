import React from 'react';
import { Composition, staticFile } from 'remotion';
import { PromoVideo, type PromoProps } from './PromoVideo';
import type { Timeline } from './types';
import { FRAME_SIZE } from './camera';

export const FPS = 60;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="QylatPromo"
      component={PromoVideo}
      fps={FPS}
      width={1080}
      height={1920}
      durationInFrames={FPS * 5}
      defaultProps={{ timeline: null, videoDurationMs: 0 }}
      calculateMetadata={async () => {
        const res = await fetch(staticFile('tour/timeline.json'));
        if (!res.ok) return { props: { timeline: null, videoDurationMs: 0 } };
        const timeline = (await res.json()) as Timeline;
        const videoDurationMs = timeline.durationMs;
        const size = FRAME_SIZE[timeline.format ?? 'landscape'];
        return {
          durationInFrames: Math.max(1, Math.floor((videoDurationMs / 1000) * FPS)),
          width: size.w,
          height: size.h,
          props: { timeline, videoDurationMs },
        };
      }}
    />
  );
};
