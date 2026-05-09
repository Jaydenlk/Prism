import type { ReactNode } from 'react';

type BadgeVariant = 'amber' | 'teal' | 'rust' | 'plum' | 'neutral';

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
}

const variantStyles: Record<BadgeVariant, { color: string; background: string }> = {
  amber:   { color: '#B8803A', background: '#F5EDDC' },
  teal:    { color: '#4E7C6E', background: '#DAE9E4' },
  rust:    { color: '#9B4A35', background: '#F3E1DA' },
  plum:    { color: '#7A4E58', background: '#EFE2E6' },
  neutral: { color: '#6B675E', background: 'rgba(28,27,24,0.08)' },
};

export function Badge({ variant = 'neutral', children }: BadgeProps) {
  const { color, background } = variantStyles[variant];
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        color,
        background,
      }}
    >
      {children}
    </span>
  );
}
