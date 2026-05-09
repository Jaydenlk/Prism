import type { MouseEvent } from 'react';
import { Badge } from '@/components/Badge/Badge';
import { Button } from '@/components/Button/Button';
import { getSourceBadge } from './utils';
import styles from './SkillCard.module.css';

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

  const sourceBadge = getSourceBadge(source);

  return (
    <article className={styles.card} onClick={onClick}>
      <div className={styles.body}>
        <div className={styles.titleRow}>
          <span className={styles.name}>{name}</span>
          <Badge variant={sourceBadge.variant}>{sourceBadge.label}</Badge>
          {installed && <Badge variant="teal">已安装</Badge>}
        </div>
        <p className={styles.description}>{description || '暂无描述'}</p>
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
