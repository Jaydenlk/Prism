import { useState, useEffect } from 'react';
import type { PersonaInfo, ThinkTankConfig, ThinkTankDiscussionMode } from '@/api/types';
import * as api from '@/api/client';
import { Icon } from '@/components/Icon/Icon';
import styles from './ThinkTankPanel.module.css';

const CN_NAMES: Record<string, string> = {
  'buffett-perspective': '巴菲特',
  'munger-skill': '芒格',
  'elon-musk-skill': '马斯克',
  'steve-jobs-skill': '乔布斯',
  'feynman-skill': '费曼',
  'naval-skill': '纳瓦尔',
  'taleb-skill': '塔勒布',
  'trump-skill': '特朗普',
  'zhang-yiming-skill': '张一鸣',
  'zhangxuefeng-skill': '张雪峰',
  'duan-yongping-skill': '段永平',
  'darwin-skill': '达尔文',
  'nuwa-skill': '女娲',
  'nuwa-creator': '女娲',
  'davinci-evolver': '达芬奇',
  'zizek-skill': '齐泽克',
  'guodegang-skills': '郭德纲',
  'maoxuan-skill': '毛选',
  'bazi-skill': '八字',
  'Master-skill': '佛学大师',
  'diamond-sutra-skill': '金刚经',
  'xinqingnian-skill': '新青年',
  'yongledadian-skill': '永乐大典',
  'retail-investors': '韭菜',
  'x-mentor-skill': 'X导师',
  'blogger-distiller': '博主蒸馏器',
};

const CN_DESCRIPTIONS: Record<string, string> = {
  'buffett-perspective': '价值投资 · 护城河 · 安全边际',
  'munger-skill': '多元思维模型 · 逆向思考 · 认知偏误',
  'elon-musk-skill': '第一性原理 · 成本拆解 · 激进迭代',
  'steve-jobs-skill': '极致产品 · 设计美学 · 战略聚焦',
  'feynman-skill': '费曼学习法 · 科学思维 · 简化复杂',
  'naval-skill': '财富杠杆 · 人生哲学 · 判断力',
  'taleb-skill': '反脆弱 · 风险管理 · 不确定性',
  'trump-skill': '谈判术 · 权力博弈 · 传播策略',
  'zhang-yiming-skill': '字节跳动 · 产品思维 · 组织管理',
  'zhangxuefeng-skill': '教育规划 · 职业选择 · 阶层流动',
  'duan-yongping-skill': '本分 · 长期主义 · 买公司就是买未来',
  'darwin-skill': '进化论 · 适应性 · 自然选择',
  'nuwa-creator': '人格蒸馏 · 创造 persona skill',
  'davinci-evolver': '自我进化 · 更新已有 persona',
  'zizek-skill': '批判理论 · 意识形态分析 · 颠覆常识',
  'maoxuan-skill': '矛盾分析 · 战略思维 · 群众路线',
};

interface Preset {
  name: string;
  description: string;
  slugs: string[];
}

const PRESETS: Preset[] = [
  {
    name: '💰 投资决策团',
    description: '价值投资+逆向思维+风险管理+财富哲学',
    slugs: ['buffett-perspective', 'munger-skill', 'taleb-skill', 'naval-skill'],
  },
  {
    name: '🚀 创业战略团',
    description: '第一性原理+极致产品+数据驱动+长期主义',
    slugs: ['elon-musk-skill', 'steve-jobs-skill', 'zhang-yiming-skill', 'duan-yongping-skill'],
  },
  {
    name: '📚 学习方法团',
    description: '费曼学习法+多元思维+职业规划',
    slugs: ['feynman-skill', 'munger-skill', 'zhangxuefeng-skill'],
  },
  {
    name: '⚖️ 风险评估团',
    description: '反脆弱+认知偏误+安全边际+谈判博弈',
    slugs: ['taleb-skill', 'munger-skill', 'buffett-perspective', 'trump-skill'],
  },
  {
    name: '🧭 人生规划团',
    description: '财富哲学+科学思维+职业规划+本分',
    slugs: ['naval-skill', 'feynman-skill', 'zhangxuefeng-skill', 'duan-yongping-skill'],
  },
  {
    name: '🔥 颠覆者联盟',
    description: '第一性原理+批判理论+矛盾分析+谈判术',
    slugs: ['elon-musk-skill', 'zizek-skill', 'maoxuan-skill', 'trump-skill'],
  },
];

function displayName(slug: string, original: string): string {
  return CN_NAMES[slug] ?? original;
}

function displayDesc(slug: string, original: string): string {
  return CN_DESCRIPTIONS[slug] ?? original;
}

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

  function applyPreset(preset: Preset) {
    const available = new Set(personas.map(p => p.slug));
    const valid = preset.slugs.filter(s => available.has(s));
    setSelected(new Set(valid));
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
            <button className={`${styles.modeBtn} ${mode === 'debate' ? styles.modeBtnActive : ''}`} onClick={() => setMode('debate')}>辩论式</button>
            <button className={`${styles.modeBtn} ${mode === 'delphi' ? styles.modeBtnActive : ''}`} onClick={() => setMode('delphi')}>德尔菲式</button>
          </div>
        </div>

        {/* Presets */}
        <div className={styles.presetSection}>
          <span className={styles.presetLabel}>预设组合</span>
          <div className={styles.presetGrid}>
            {PRESETS.map(preset => (
              <button key={preset.name} className={styles.presetBtn} onClick={() => applyPreset(preset)}>
                <span className={styles.presetName}>{preset.name}</span>
                <span className={styles.presetDesc}>{preset.description}</span>
              </button>
            ))}
          </div>
        </div>

        <p className={styles.hint}>
          选择 2-5 位智囊（已选 {selected.size}）
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
                <span className={styles.personaName}>{displayName(p.slug, p.name)}</span>
                <span className={styles.personaDesc}>{displayDesc(p.slug, p.description)}</span>
              </button>
            ))}
          </div>
        )}

        <div className={styles.footer}>
          <button className={styles.cancelBtn} onClick={onCancel}>取消</button>
          <button className={styles.confirmBtn} onClick={handleConfirm} disabled={!canConfirm}>开始讨论</button>
        </div>
      </div>
    </div>
  );
}
