import React from 'react';
import type { Layout } from './camera';
import { BODY_FONT } from './theme';

export const BrowserWindow: React.FC<{ url: string; layout: Layout; children: React.ReactNode }> = ({
  url,
  layout,
  children,
}) => {
  const { window: win, content, headerH, radius, format } = layout;
  const phone = format === 'portrait';
  return (
    <div
      style={{
        position: 'absolute',
        left: win.x,
        top: win.y,
        width: win.w,
        height: win.h,
        backgroundColor: '#ffffff',
        borderRadius: radius,
        overflow: 'hidden',
        boxShadow: '0 30px 70px -20px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.08)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          height: headerH,
          backgroundColor: '#f3f4f6',
          display: 'flex',
          alignItems: 'center',
          padding: phone ? '0 22px' : '0 20px',
          borderBottom: '1px solid #e5e7eb',
          fontFamily: BODY_FONT,
          flexShrink: 0,
        }}
      >
        {phone ? null : (
          <div style={{ display: 'flex', gap: 8, width: 120 }}>
            <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ff5f56' }} />
            <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ffbd2e' }} />
            <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#27c93f' }} />
          </div>
        )}
        <div
          style={{
            margin: '0 auto',
            backgroundColor: '#e5e7eb',
            padding: phone ? '12px 28px' : '8px 24px',
            minWidth: phone ? undefined : 520,
            width: phone ? '100%' : undefined,
            textAlign: 'center',
            borderRadius: phone ? 24 : 8,
            fontSize: phone ? 28 : 15,
            color: '#374151',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          <span style={{ color: '#9ca3af', marginRight: 8 }}>🔒</span>
          {url}
        </div>
        {phone ? null : <div style={{ width: 120 }} />}
      </div>
      <div style={{ width: content.w, height: content.h, position: 'relative', overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
};
