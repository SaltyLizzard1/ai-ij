import React from 'react';
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { BACKDROP, BODY_FONT, CREAM, GOLD, GOLD_GRADIENT, HEADING_FONT } from './theme';

const Rule: React.FC = () => (
  <div
    style={{
      width: 320,
      height: 3,
      margin: '28px auto',
      background: 'linear-gradient(90deg, transparent 0%, #C9A030 25%, #F5E070 50%, #C9A030 75%, transparent 100%)',
    }}
  />
);

const GoldText: React.FC<{ size: number; children: React.ReactNode }> = ({ size, children }) => (
  <div
    style={{
      fontFamily: HEADING_FONT,
      fontWeight: 700,
      fontSize: size,
      lineHeight: 1.05,
      background: GOLD_GRADIENT,
      WebkitBackgroundClip: 'text',
      backgroundClip: 'text',
      color: 'transparent',
      padding: '0 40px 8px',
    }}
  >
    {children}
  </div>
);

const Card: React.FC<{ solid: number; veil: number; children: React.ReactNode }> = ({ solid, veil, children }) => (
  <>
    {/* Solid brand backdrop while the page loads, then a veil over the site. */}
    <AbsoluteFill style={{ background: BACKDROP, opacity: solid }} />
    <AbsoluteFill style={{ background: 'rgba(45,26,0,0.62)', opacity: veil }} />
    <AbsoluteFill
      style={{
        opacity: Math.max(solid, veil),
        justifyContent: 'center',
        alignItems: 'center',
        textAlign: 'center',
        fontFamily: BODY_FONT,
        color: CREAM,
        textShadow: '0 4px 24px rgba(0,0,0,0.5)',
      }}
    >
      {children}
    </AbsoluteFill>
  </>
);

/** Hook card. Solid for the first second (the page is still loading behind it), then a veil, then gone. */
export const IntroCard: React.FC<{ durationInFrames: number }> = ({ durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = spring({ frame, fps, config: { damping: 20, stiffness: 60 } });
  const solid = interpolate(frame, [fps * 1.2, fps * 2.0], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const veil = interpolate(frame, [fps * 1.2, fps * 2.0, durationInFrames - 20, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <Card solid={solid} veil={veil}>
      <div style={{ transform: `translateY(${(1 - rise) * 30}px)`, opacity: rise }}>
        <div style={{ fontSize: 22, letterSpacing: 6, textTransform: 'uppercase', color: GOLD }}>
          quityourlifeandtravel.com
        </div>
        <Rule />
        <GoldText size={132}>Quit Your Life &amp; Travel</GoldText>
        <div style={{ fontFamily: HEADING_FONT, fontWeight: 700, fontSize: 68, color: CREAM, marginTop: 10 }}>
          Your Thailand Escape Plan
        </div>
      </div>
    </Card>
  );
};

/** Call to action over the homepage. Never fully solid, so the site stays visible behind it. */
export const OutroCard: React.FC<{ durationInFrames: number }> = ({ durationInFrames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const veil = interpolate(frame, [0, 24], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const rise = spring({ frame: frame - 8, fps, config: { damping: 20, stiffness: 60 } });
  const pulse = 1 + 0.02 * Math.sin((frame / fps) * Math.PI * 1.5);
  void durationInFrames;
  return (
    <Card solid={0} veil={veil}>
      <div style={{ transform: `translateY(${(1 - rise) * 30}px)`, opacity: rise }}>
        <div style={{ fontFamily: HEADING_FONT, fontWeight: 700, fontSize: 56, color: CREAM, opacity: 0.9 }}>
          Stop waiting for the perfect moment.
        </div>
        <Rule />
        <GoldText size={92}>Visit quityourlifeandtravel.com</GoldText>
        <div
          style={{
            display: 'inline-block',
            marginTop: 36,
            padding: '20px 48px',
            borderRadius: 14,
            background: GOLD_GRADIENT,
            color: '#2D1A00',
            fontFamily: BODY_FONT,
            fontWeight: 700,
            fontSize: 34,
            letterSpacing: 0.5,
            border: '1.5px solid #2D1A00',
            boxShadow: '0 16px 40px rgba(0,0,0,0.4)',
            transform: `scale(${pulse})`,
          }}
        >
          Start Your Free Assessment Now
        </div>
      </div>
    </Card>
  );
};
