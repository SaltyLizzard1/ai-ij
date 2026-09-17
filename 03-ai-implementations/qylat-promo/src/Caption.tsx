import React from 'react';
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { BODY_FONT, CREAM, GOLD, GOLD_GRADIENT, HEADING_FONT } from './theme';

export const Caption: React.FC<{
  title: string;
  subtitle?: string;
  eyebrow: string;
  durationInFrames: number;
}> = ({ title, subtitle, eyebrow, durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const portrait = height > width;
  const k = portrait ? 0.78 : 1;
  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 90 } });
  const exit = interpolate(frame, [durationInFrames - 14, durationInFrames - 2], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const opacity = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [28, 0]);

  return (
    <div
      style={{
        position: 'absolute',
        left: portrait ? 48 : 72,
        right: portrait ? 48 : undefined,
        bottom: portrait ? 96 : 64,
        maxWidth: portrait ? undefined : 1100,
        opacity,
        transform: `translateY(${y}px)`,
        padding: '22px 34px 24px',
        borderRadius: 16,
        background: 'rgba(45,26,0,0.78)',
        backdropFilter: 'blur(12px)',
        border: `1px solid ${GOLD}`,
        boxShadow: '0 20px 50px rgba(0,0,0,0.45)',
      }}
    >
      <div
        style={{
          fontFamily: BODY_FONT,
          fontSize: 17 * k,
          letterSpacing: 3,
          textTransform: 'uppercase',
          color: GOLD,
          marginBottom: 6,
        }}
      >
        {eyebrow}
      </div>
      <div
        style={{
          fontFamily: HEADING_FONT,
          fontWeight: 700,
          fontSize: 62 * k,
          lineHeight: 1.05,
          background: GOLD_GRADIENT,
          WebkitBackgroundClip: 'text',
          backgroundClip: 'text',
          color: 'transparent',
          paddingBottom: 4,
        }}
      >
        {title}
      </div>
      {subtitle ? (
        <div style={{ fontFamily: BODY_FONT, fontSize: 27 * k, color: CREAM, opacity: 0.92, marginTop: 6, lineHeight: 1.3 }}>
          {subtitle}
        </div>
      ) : null}
    </div>
  );
};
