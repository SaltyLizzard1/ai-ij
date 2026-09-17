import React from 'react';
import { Composition, staticFile } from 'remotion';
import { PromoVideo, type PromoProps } from './PromoVideo';
import { CUTS, FORMATS, variantId, type Cut, type Format, type Timeline } from './types';
import { FRAME_SIZE } from './camera';

export const FPS = 60;

const Variant: React.FC<{ cut: Cut; format: Format }> = ({ cut, format }) => {
  const id = variantId(cut, format);
  const size = FRAME_SIZE[format];
  return (
    <Composition
      id={id}
      component={PromoVideo}
      fps={FPS}
      width={size.w}
      height={size.h}
      durationInFrames={FPS * 5}
      defaultProps={{ timeline: null, videoDurationMs: 0 }}
      calculateMetadata={async () => {
        const res = await fetch(staticFile(`tour/${id}/timeline.json`));
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

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {CUTS.map((cut) => FORMATS.map((format) => <Variant key={variantId(cut, format)} cut={cut} format={format} />))}
    </>
  );
};
