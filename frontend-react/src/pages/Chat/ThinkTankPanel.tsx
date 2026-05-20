import { useState, useEffect } from 'react';
import type { PersonaInfo, ThinkTankConfig, ThinkTankDiscussionMode } from '@/api/types';
import * as api from '@/api/client';
import { Icon } from '@/components/Icon/Icon';
import styles from './ThinkTankPanel.module.css';

interface ThinkTankPanelProps {
  onConfirm: (config: ThinkTankConfig) => void;
  onCancel: () => void;
}

export function ThinkTankPanel({ onConfirm, onCancel }: ThinkTankPanelProps) {
  const [personas, setPersonas] = useState<PersonaInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<ThinkTankDiscussionMode>('debate');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.personas.listAvailable().then(list => {
      setPersonas(list);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  function togglePersona(slug: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(slug)) {
        next.delete(slug);
      } else if (next.size < 5) {
        next.add(slug);
      }
      return next;
    });
  }

  function handleConfirm() {
    if (selected.size < 2) return;
    const selectedPersonas = personas.filter(p => selected.has(p.slug));
    onConfirm({ personas: selectedPersonas, mode });
  }

  const canConfirm = selected.size >= 2 && selected.size <= 5;

  return (
    <div className={styles.overlay}>
      <div className={styles.panel}>
        <div className={styles.header}>
          <span className={styles.title}>智囊团配置</span>
          <button className={styles.closeBtn} onClick={onCancel}>
            <Icon name="close" size={16} />
          </button>
        </div>

        <div className={styles.modeRow}>
          <span className={styles.modeLabel}>讨论模式</span>
          <div className={styles.modeButtons}>
            <button
              className={`${styles.modeBtn} ${mode === 'debate' ? styles.modeBtnActive : ''}`}
              onClick={() => setMode('debate')}
            >
              辩论式
            </button>
            <button
              className={`${styles.modeBtn} ${mode === 'delphi' ? styles.modeBtnActive : ''}`}
              onClick={() => setMode('delphi')}
            >
              德尔菲式
            </button>
          </div>
        </div>

        <p className={styles.hint}>
          选择 2-5 个 Persona（已选 {selected.size}）
        </p>

        {loading ? (
          <div className={styles.loading}>加载中…</div>
        ) : (
          <div className={styles.personaGrid}>
            {personas.map(p => (
              <button
                key={p.slug}
                className={`${styles.personaCard} ${selected.has(p.slug) ? styles.personaCardSelected : ''} ${!selected.has(p.slug) && selected.size >= 5 ? styles.personaCardDisabled : ''}`}
                onClick={() => togglePersona(p.slug)}
              >
                <span className={styles.personaName}>{p.name}</span>
                <span className={styles.personaDesc}>{p.description}</span>
              </button>
            ))}
          </div>
        )}

        <div className={styles.footer}>
          <button className={styles.cancelBtn} onClick={onCancel}>取消</button>
          <button
            className={styles.confirmBtn}
            onClick={handleConfirm}
            disabled={!canConfirm}
          >
            开始讨论
          </button>
        </div>
      </div>
    </div>
  );
}
