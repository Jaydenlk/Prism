import { PrismGlyph } from '@/components/Icon/Icon';
import styles from './EmptyState.module.css';

interface EmptyStateProps {
  onSelectExample: (text: string) => void;
}

const EXAMPLES = [
  '读一下 executor/,帮我理解 TAOR 主循环是怎么转的',
  '上周的 runs 表现如何?哪里花钱最多?',
  '写一份 2026 年 Harness Engineering 的内部简报',
  '帮我搞一个只读 shell 的 Skill,就叫 readonly-shell',
];

export function EmptyState({ onSelectExample }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      flex: 1,
      padding: '40px 24px',
      textAlign: 'center',
    }}>
      <div style={{ color: 'var(--ink-3)', marginBottom: 20 }}>
        <PrismGlyph size={120} />
      </div>
      <h3 style={{
        fontFamily: 'var(--serif)',
        fontSize: 20,
        color: 'var(--ink)',
        fontWeight: 500,
        marginBottom: 10,
      }}>
        随便聊点什么。
      </h3>
      <p style={{
        fontSize: 14,
        color: 'var(--ink-3)',
        maxWidth: 480,
        lineHeight: 1.6,
        marginBottom: 24,
      }}>
        我会把你的问题分派给对的 Agent —— 研究、规划、执行或验证。不用想太多。
      </p>
      <div style={{ fontSize: 13, color: 'var(--ink-4)', marginBottom: 14 }}>
        或者从这里开始
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 480 }}>
        {EXAMPLES.map((ex, i) => (
          <button
            key={i}
            onClick={() => onSelectExample(ex)}
            className={styles.exampleItem}
            style={{
              padding: '10px 16px',
              border: '1px solid var(--line)',
              borderRadius: 10,
              cursor: 'pointer',
              background: 'transparent',
              fontSize: 13,
              color: 'var(--ink-2)',
              textAlign: 'left',
              fontFamily: 'var(--serif)',
              fontStyle: 'italic',
              lineHeight: 1.5,
              transition: 'background 0.15s',
              maxWidth: 360,
              alignSelf: 'center',
              width: '100%',
              animationDelay: `${i * 80}ms`,
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
