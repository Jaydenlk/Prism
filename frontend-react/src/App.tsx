import { Icon, PrismMark, PrismGlyph } from './components/Icon/Icon';
import type { IconName } from './components/Icon/Icon';
import { palette, typography, shadows } from './theme/tokens';

const ALL_ICONS: IconName[] = [
  'search', 'plus', 'chat', 'sessions', 'settings', 'usage',
  'skills', 'plugin', 'admin', 'chevron', 'close', 'check',
  'attach', 'shield', 'alert', 'info', 'clock', 'book',
  'terminal', 'folder', 'pin', 'globe', 'copy', 'fork',
  'refresh', 'arrowUp', 'arrowRight', 'more', 'layers', 'send',
  'eye', 'download', 'upload', 'filter', 'flask', 'flow',
  'link', 'menu', 'sparkle',
];

export function App() {
  return (
    <div style={{ padding: 32, fontFamily: typography.serif, background: palette.bg, minHeight: '100%' }}>
      {/* Design token card */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.md,
        marginBottom: 32,
        maxWidth: 600,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <PrismMark size={32} />
          <h1 style={{ fontFamily: typography.serif, fontSize: 22, fontWeight: 500, color: palette.ink }}>
            Prism Design System
          </h1>
        </div>
        <p style={{ color: palette.amber, fontFamily: typography.serif, fontSize: 15, marginBottom: 8 }}>
          Amber accent — document / paper tone
        </p>
        <p style={{ color: palette.ink3, fontFamily: typography.mono, fontSize: 12 }}>
          Monospace: {typography.mono}
        </p>
        <div style={{ marginTop: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Object.entries(palette).map(([key, value]) => (
            <div key={key} style={{
              background: value,
              border: `1px solid ${palette.lineStrong}`,
              borderRadius: 6,
              padding: '4px 8px',
              fontSize: 11,
              fontFamily: typography.mono,
              color: palette.ink,
            }}>
              {key}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 16 }}>
          <PrismGlyph size={80} />
        </div>
      </div>

      {/* Icon grid */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Icons ({ALL_ICONS.length})
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
          {ALL_ICONS.map((name) => (
            <div key={name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <Icon name={name} size={20} />
              <span style={{ fontSize: 10, color: palette.ink3, fontFamily: typography.mono }}>{name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
