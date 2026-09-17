import React, { useMemo } from 'react';
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { loadFont } from '@remotion/fonts';
import { BrowserWindow } from './BrowserWindow';
import { Caption } from './Caption';
import { IntroCard, OutroCard } from './TitleCards';
import { cameraAtFrame, cameraForBox, type CameraKey } from './camera';
import { BACKDROP } from './theme';
import type { Timeline } from './types';

loadFont({
  family: 'Cormorant Garamond',
  url: staticFile('fonts/CormorantGaramond-700.ttf'),
  weight: '700',
});

export interface PromoProps extends Record<string, unknown> {
  timeline: Timeline | null;
  videoDurationMs: number;
}

export const PromoVideo: React.FC<PromoProps> = ({ timeline, videoDurationMs }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const model = useMemo(() => {
    if (!timeline) return null;
    // Recording starts a little after the page is created. Everything
    // recorded in wall-clock time shifts earlier by that lag.
    const lag = videoDurationMs > 0 ? Math.max(0, timeline.wallMs - videoDurationMs) : 0;
    const toFrame = (t: number) => Math.round(((t - lag + timeline.syncOffsetMs) / 1000) * fps);

    const cameraKeys: CameraKey[] = [];
    const urls: { frame: number; path: string }[] = [];
    const scenes: { frame: number; id: string; eyebrow: string; title: string; subtitle?: string }[] = [];
    for (const e of timeline.events) {
      const f = Math.max(0, toFrame(e.t));
      if (e.type === 'zoom') cameraKeys.push({ frame: f, target: cameraForBox(e.box, timeline.viewport, e.level) });
      else if (e.type === 'zoomOut') cameraKeys.push({ frame: f, target: { scale: 1, tx: 0, ty: 0 } });
      else if (e.type === 'url') urls.push({ frame: f, path: e.path });
      else if (e.type === 'scene')
        scenes.push({ frame: f, id: e.id, eyebrow: e.eyebrow ?? timeline.host, title: e.title, subtitle: e.subtitle });
    }
    const introFrames = Math.round((timeline.introMs / 1000) * fps);
    const outroFrames = Math.round((timeline.outroMs / 1000) * fps);
    const outroStart = Math.max(introFrames, durationInFrames - outroFrames);
    const captions = scenes.map((s, i) => {
      const start = Math.max(s.frame, i === 0 ? introFrames - 12 : s.frame);
      const end = i + 1 < scenes.length ? scenes[i + 1].frame : outroStart + 12;
      return { ...s, start, duration: Math.max(1, end - start) };
    });
    return { cameraKeys, urls, captions, introFrames, outroFrames, outroStart };
  }, [timeline, videoDurationMs, fps, durationInFrames]);

  if (!timeline || !model) {
    return (
      <AbsoluteFill style={{ background: BACKDROP, color: '#FBF6E3', justifyContent: 'center', alignItems: 'center', fontSize: 40 }}>
        No recording yet. Run `npm run record` first.
      </AbsoluteFill>
    );
  }

  const cam = cameraAtFrame(model.cameraKeys, frame, fps);
  const currentPath = [...model.urls].reverse().find((u) => u.frame <= frame)?.path ?? '/';
  const url = timeline.host + (currentPath === '/' ? '' : currentPath);

  return (
    <AbsoluteFill style={{ background: BACKDROP }}>
      <AbsoluteFill
        style={{
          transform: `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.scale})`,
          transformOrigin: '50% 50%',
        }}
      >
        <BrowserWindow url={url}>
          <OffthreadVideo
            src={staticFile(timeline.video)}
            muted
            style={{ width: '100%', height: '100%', objectFit: 'fill', display: 'block' }}
          />
        </BrowserWindow>
      </AbsoluteFill>

      {model.captions.map((c) => (
        <Sequence key={c.id} from={c.start} durationInFrames={c.duration} name={`caption:${c.id}`}>
          <Caption title={c.title} subtitle={c.subtitle} eyebrow={c.eyebrow} durationInFrames={c.duration} />
        </Sequence>
      ))}

      {model.captions.map((c) => {
        const file = timeline.narration[c.id];
        return file ? (
          <Sequence key={`audio:${c.id}`} from={c.start} name={`narration:${c.id}`}>
            <Audio src={staticFile(file)} />
          </Sequence>
        ) : null;
      })}

      {timeline.music ? <Audio src={staticFile(timeline.music)} volume={0.14} loop /> : null}

      <Sequence from={0} durationInFrames={model.introFrames} name="intro">
        <IntroCard durationInFrames={model.introFrames} />
      </Sequence>
      <Sequence from={model.outroStart} name="outro">
        <OutroCard durationInFrames={model.outroFrames} />
      </Sequence>
    </AbsoluteFill>
  );
};
