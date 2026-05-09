import { useState } from 'react';
import { Icon } from '@/components/Icon/Icon';

interface ThinkingBlockProps {
  content: string;
}

const containerStyle: React.CSSProperties = {
  borderLeft: '2px solid var(--ink-4)',
  paddingLeft: 12,
  color: 'var(--ink-3)',
  fontSize: 13,
  margin: '8px 0',
};

const triggerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  cursor: 'pointer',
  userSelect: 'none',
  fontStyle: 'italic',
};

const contentStyle: React.CSSProperties = {
  marginTop: 8,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  lineHeight: 1.55,
};

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [open, setOpen] = useState(false);

  return (
    <div style={containerStyle}>
      <div style={triggerStyle} onClick={() => setOpen(o => !o)}>
        <Icon
          name="chevron"
          size={11}
          style={{ transition: 'transform 0.2s', transform: open ? 'rotate(90deg)' : '' }}
        />
        思考过程
      </div>
      {open && (
        <div style={contentStyle}>{content}</div>
      )}
    </div>
  );
}
