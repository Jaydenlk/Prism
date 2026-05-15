import { useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import styles from './ThinkingBlock.module.css';

interface ThinkingBlockProps {
  content: string;
}

export function ThinkingBlock({ content }: ThinkingBlockProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.container}>
      <div className={styles.trigger} onClick={() => setOpen(o => !o)}>
        <Icon
          name="chevron"
          size={11}
          className={`${styles.chevron}${open ? ` ${styles.chevronOpen}` : ''}`}
        />
        思考过程
      </div>
      <div className={`${styles.expandWrapper}${open ? ` ${styles.open}` : ''}`}>
        <div className={styles.expandInner}>
          <div className={styles.content}>{content}</div>
        </div>
      </div>
    </div>
  );
}
