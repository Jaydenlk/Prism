import type { MouseEvent } from 'react';
import { Badge } from '@/components/Badge/Badge';
import { Button } from '@/components/Button/Button';

type BadgeVariant = 'amber' | 'teal' | 'rust' | 'plum' | 'neutral';

function sourceBadgeVariant(source: string): BadgeVariant {
  if (source === 'local') return 'teal';
  if (source === 'github') return 'plum';
  if (source === 'marketplace') return 'amber';
  return 'neutral';
}

function sourceLabel(source: string): string {
  if (source === 'local') return '本地';
  if (source === 'github') return 'GitHub';
  if (source === 'marketplace') return '市场';
  return source;
}

export interface SkillCardProps {
  name: string;
  description: string;
  source: string;
  sourceUrl: string | null;
  installed: boolean;
  score?: number;
  onInstall: () => void;
  onUninstall: () => void;
  onClick: () => void;
}

export function SkillCard({
  name,
  description,
  source,
  installed,
  onInstall,
  onUninstall,
  onClick,
}: SkillCardProps) {
  function handleAction(e: MouseEvent) {
    e.stopPropagation();
    if (installed) onUninstall();
    else onInstall();
  }

  return (
    <article
      onClick={onClick}
      style={{
        background: 'var(--paper)',
        border: '1px solid var(--line)',
        borderRadius: 16,
        padding: '16px 20px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        transition: 'box-shadow 0.15s ease, border-color 0.15s ease',
      }}
      onMouseEnter={e => {
        (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-2)';
        (e.currentTarget as HTMLElement).style.borderColor = 'var(--line-strong)';
      }}
      onMouseLeave={e => {
        (e.currentTarget as HTMLElement).style.boxShadow = 'none';
        (e.currentTarget as HTMLElement).style.borderColor = 'var(--line)';
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
          <span
            style={{
              fontFamily: 'var(--serif)',
              fontSize: 15,
              fontWeight: 500,
              color: 'var(--ink)',
              lineHeight: 1.3,
            }}
          >
            {name}
          </span>
          <Badge variant={sourceBadgeVariant(source)}>{sourceLabel(source)}</Badge>
          {installed && <Badge variant="teal">已安装</Badge>}
        </div>
        <p
          style={{
            fontSize: 13,
            color: 'var(--ink-3)',
            lineHeight: 1.5,
            margin: 0,
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {description || '暂无描述'}
        </p>
      </div>

      <Button
        variant={installed ? 'ghost' : 'primary'}
        size="sm"
        onClick={handleAction}
        style={{ flexShrink: 0, alignSelf: 'center' }}
      >
        {installed ? '卸载' : '安装'}
      </Button>
    </article>
  );
}
