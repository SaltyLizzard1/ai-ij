import React from 'react';
import { Composition, staticFile } from 'remotion';
import { PromoVideo, type PromoProps } from './PromoVideo';
import type { Timeline } from './types';

export const FPS = 60;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="QylatPromo"
      component={PromoVideo}
      fps={FPS}
      width={1920}
      height={1080}
      durationInFrames={FPS * 5}
      defaultProps={{ timeline: null, videoDurationMs: 0 }}
      calculateMetadata={async () => {
        const res = await fetch(staticFile('tour/timeline.json'));
        if (!res.ok) return { props: { timeline: null, videoDurationMs: 0 } };
        const timeline = (await res.json()) as Timeline;
        const videoDurationMs = timeline.durationMs;
        return {
          durationInFrames: Math.max(1, Math.floor((videoDurationMs / 1000) * FPS)),
          props: { timeline, videoDurationMs },
        };
      }}
    />
  );
};
