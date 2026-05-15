import { useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import { Badge } from '@/components/Badge/Badge';
import { Spinner } from '@/components/Spinner/Spinner';
import { CodeBlock } from './CodeBlock';
import styles from './ToolCard.module.css';

interface ToolCardProps {
  name: string;
  status: 'running' | 'ok' | 'error';
  input?: string;
  output?: string;
  duration?: number;
  isError?: boolean;
}

export function ToolCard({ name, status, input, output, duration, isError }: ToolCardProps) {
  const [open, setOpen] = useState(false);
  const hasBody = !!(input || output);

  return (
    <div className={styles.container}>
      <div className={styles.header} onClick={() => hasBody && setOpen(o => !o)}>
        <Icon
          name="chevron"
          size={11}
          className={`${styles.chevron}${open ? ` ${styles.chevronOpen}` : ''}`}
          style={{ opacity: hasBody ? 1 : 0.3 }}
        />
        <Icon name="terminal" size={13} className={styles.toolIcon} />
        <span className={styles.toolName}>{name}</span>
        <div className={styles.statusRow}>
          {status === 'running' && (
            <Badge variant="amber">
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Spinner size={10} />
                运行中
              </span>
            </Badge>
          )}
          {status === 'ok' && !isError && <Badge variant="teal">完成</Badge>}
          {(status === 'error' || isError) && <Badge variant="rust">错误</Badge>}
          {duration !== undefined && (
            <span className={styles.duration}>{duration}ms</span>
          )}
        </div>
      </div>

      {hasBody && (
        <div className={`${styles.expandWrapper}${open ? ` ${styles.open}` : ''}`}>
          <div className={styles.expandInner}>
            <div className={styles.body}>
              {input && (
                <>
                  <div className={styles.sectionLabel}>输入</div>
                  <CodeBlock code={input} language="json" />
                </>
              )}
              {output && (
                <>
                  <div className={styles.sectionLabel}>输出</div>
                  <pre className={styles.outputPre}>{output}</pre>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
