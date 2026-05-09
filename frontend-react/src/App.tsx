import { useState } from 'react';
import { Icon, PrismMark, PrismGlyph } from './components/Icon/Icon';
import type { IconName } from './components/Icon/Icon';
import { palette, typography, shadows } from './theme/tokens';
import { Button } from './components/Button/Button';
import { Badge } from './components/Badge/Badge';
import { Spinner } from './components/Spinner/Spinner';
import { Modal } from './components/Modal/Modal';
import { ToastProvider, useToast } from './components/Toast/ToastContext';
import { Toast } from './components/Toast/Toast';
import { Dropdown } from './components/Dropdown/Dropdown';

const ALL_ICONS: IconName[] = [
  'search', 'plus', 'chat', 'sessions', 'settings', 'usage',
  'skills', 'plugin', 'admin', 'chevron', 'close', 'check',
  'attach', 'shield', 'alert', 'info', 'clock', 'book',
  'terminal', 'folder', 'pin', 'globe', 'copy', 'fork',
  'refresh', 'arrowUp', 'arrowRight', 'more', 'layers', 'send',
  'eye', 'download', 'upload', 'filter', 'flask', 'flow',
  'link', 'menu', 'sparkle',
];

function ToastTriggers() {
  const { addToast } = useToast();
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <Button variant="primary" size="sm" onClick={() => addToast('Info message', 'info')}>
        Toast info
      </Button>
      <Button variant="ghost" size="sm" onClick={() => addToast('Action completed', 'success')}>
        Toast success
      </Button>
      <Button variant="danger" size="sm" onClick={() => addToast('Something went wrong', 'error')}>
        Toast error
      </Button>
    </div>
  );
}

function Showcase() {
  const [modalOpen, setModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  function simulateLoad() {
    setLoading(true);
    setTimeout(() => setLoading(false), 2000);
  }

  return (
    <div style={{ padding: 32, fontFamily: typography.serif, background: palette.bg, minHeight: '100%' }}>

      {/* Header */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.md,
        marginBottom: 24,
        maxWidth: 700,
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

      {/* Buttons */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        marginBottom: 24,
        maxWidth: 700,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Buttons
        </h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          <Button variant="primary" size="md" icon="plus">Primary md</Button>
          <Button variant="primary" size="sm" icon="plus">Primary sm</Button>
          <Button variant="ghost" size="md" icon="settings">Ghost md</Button>
          <Button variant="ghost" size="sm">Ghost sm</Button>
          <Button variant="danger" size="md" icon="alert">Danger md</Button>
          <Button variant="danger" size="sm">Danger sm</Button>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          <Button variant="primary" loading>Loading</Button>
          <Button variant="primary" disabled>Disabled</Button>
          <Button variant="ghost" loading size="sm">Loading sm</Button>
        </div>
        <Button variant="primary" onClick={simulateLoad} loading={loading}>
          {loading ? 'Working…' : 'Simulate load (2s)'}
        </Button>
      </div>

      {/* Badges */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        marginBottom: 24,
        maxWidth: 700,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Badges
        </h2>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Badge variant="amber">amber</Badge>
          <Badge variant="teal">teal</Badge>
          <Badge variant="rust">rust</Badge>
          <Badge variant="plum">plum</Badge>
          <Badge variant="neutral">neutral</Badge>
        </div>
      </div>

      {/* Spinner */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        marginBottom: 24,
        maxWidth: 700,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Spinner
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Spinner size={12} />
          <Spinner size={16} />
          <Spinner size={24} />
          <Spinner size={32} />
        </div>
      </div>

      {/* Modal */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        marginBottom: 24,
        maxWidth: 700,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Modal
        </h2>
        <Button variant="primary" icon="plus" onClick={() => setModalOpen(true)}>
          Open Modal
        </Button>
        <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Example Modal">
          <p style={{ color: palette.ink2, fontSize: 14, lineHeight: 1.6 }}>
            This is the modal body content. Press Escape or click the backdrop to close.
          </p>
          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            <Button variant="primary" size="sm" onClick={() => setModalOpen(false)}>Confirm</Button>
            <Button variant="ghost" size="sm" onClick={() => setModalOpen(false)}>Cancel</Button>
          </div>
        </Modal>
      </div>

      {/* Toast */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        marginBottom: 24,
        maxWidth: 700,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Toast
        </h2>
        <ToastTriggers />
      </div>

      {/* Dropdown */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        marginBottom: 24,
        maxWidth: 700,
      }}>
        <h2 style={{ fontFamily: typography.serif, fontSize: 16, fontWeight: 500, color: palette.ink, marginBottom: 16 }}>
          Dropdown
        </h2>
        <Dropdown
          trigger={<Button variant="ghost" icon="more">Options</Button>}
          items={[
            {
              label: 'Edit',
              icon: <Icon name="settings" size={14} />,
              onClick: () => alert('Edit clicked'),
            },
            {
              label: 'Duplicate',
              icon: <Icon name="copy" size={14} />,
              onClick: () => alert('Duplicate clicked'),
            },
            {
              label: 'Delete',
              icon: <Icon name="close" size={14} />,
              danger: true,
              onClick: () => alert('Delete clicked'),
            },
          ]}
        />
      </div>

      {/* Icon grid */}
      <div style={{
        background: palette.paper,
        borderRadius: 12,
        padding: 24,
        boxShadow: shadows.sm,
        maxWidth: 700,
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

export function App() {
  return (
    <ToastProvider>
      <Showcase />
      <Toast />
    </ToastProvider>
  );
}
