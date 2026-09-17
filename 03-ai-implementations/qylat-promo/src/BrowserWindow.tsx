import React from 'react';
import { CONTENT, HEADER_H, WINDOW, WINDOW_POS } from './camera';
import { BODY_FONT } from './theme';

export const BrowserWindow: React.FC<{ url: string; children: React.ReactNode }> = ({ url, children }) => {
  return (
    <div
      style={{
        position: 'absolute',
        left: WINDOW_POS.x,
        top: WINDOW_POS.y,
        width: WINDOW.w,
        height: WINDOW.h,
        backgroundColor: '#ffffff',
        borderRadius: 18,
        overflow: 'hidden',
        boxShadow: '0 30px 70px -20px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.08)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          height: HEADER_H,
          backgroundColor: '#f3f4f6',
          display: 'flex',
          alignItems: 'center',
          padding: '0 20px',
          borderBottom: '1px solid #e5e7eb',
          fontFamily: BODY_FONT,
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', gap: 8, width: 120 }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ff5f56' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#ffbd2e' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#27c93f' }} />
        </div>
        <div
          style={{
            margin: '0 auto',
            backgroundColor: '#e5e7eb',
            padding: '8px 24px',
            minWidth: 520,
            textAlign: 'center',
            borderRadius: 8,
            fontSize: 15,
            color: '#374151',
            whiteSpace: 'nowrap',
          }}
        >
          <span style={{ color: '#9ca3af', marginRight: 6 }}>🔒</span>
          {url}
        </div>
        <div style={{ width: 120 }} />
      </div>
      <div style={{ width: CONTENT.w, height: CONTENT.h, position: 'relative', overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
};
