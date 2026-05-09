import { useEffect, useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import { Badge } from '@/components/Badge/Badge';
import { Button } from '@/components/Button/Button';
import { Spinner } from '@/components/Spinner/Spinner';
import { ContentRenderer } from '@/pages/Chat/ContentRenderer';
import * as api from '@/api/client';
import type { SkillPackage } from '@/api/types';
import styles from './SkillDetailPanel.module.css';

interface SkillDetailPanelProps {
  skill: SkillPackage;
  installed: boolean;
  onInstall: () => void;
  onUninstall: () => void;
  onClose: () => void;
}

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

export function SkillDetailPanel({
  skill,
  installed,
  onInstall,
  onUninstall,
  onClose,
}: SkillDetailPanelProps) {
  const [readme, setReadme] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setReadme('');
    api.skills.getReadme(skill.name, skill.source_url ?? undefined)
      .then(data => {
        if (!cancelled) setReadme(data.readme || 'README 暂不可用');
      })
      .catch(() => {
        if (!cancelled) setReadme('README 暂不可用');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [skill.name, skill.source_url]);

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.headerMeta}>
          <span className={styles.headerTitle}>{skill.name}</span>
          <div className={styles.headerBadges}>
            <Badge variant={sourceBadgeVariant(skill.source)}>{sourceLabel(skill.source)}</Badge>
            {skill.version && (
              <span className={styles.version}>v{skill.version}</span>
            )}
          </div>
        </div>
        <button className={styles.closeBtn} onClick={onClose} aria-label="关闭">
          <Icon name="close" size={14} />
        </button>
      </div>

      <div className={styles.body}>
        {skill.description && (
          <p className={styles.description}>{skill.description}</p>
        )}

        <dl className={styles.meta}>
          {skill.author && (
            <>
              <dt>作者</dt>
              <dd>{skill.author}</dd>
            </>
          )}
          {skill.source_url && (
            <>
              <dt>来源</dt>
              <dd className={styles.metaUrl}>{skill.source_url}</dd>
            </>
          )}
          {skill.license && (
            <>
              <dt>许可</dt>
              <dd>{skill.license}</dd>
            </>
          )}
        </dl>

        <div className={styles.readmeSection}>
          <div className={styles.readmeTitle}>README</div>
          {loading ? (
            <div className={styles.readmeLoading}>
              <Spinner size={16} />
            </div>
          ) : (
            <ContentRenderer content={readme} />
          )}
        </div>
      </div>

      <div className={styles.footer}>
        <Button
          variant={installed ? 'ghost' : 'primary'}
          onClick={installed ? onUninstall : onInstall}
          style={{ flex: 1, justifyContent: 'center' }}
        >
          {installed ? '卸载技能' : '安装技能'}
        </Button>
      </div>
    </div>
  );
}
