import { useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import { ContentRenderer } from './ContentRenderer';
import styles from './ThinkingModeRenderer.module.css';

interface Section {
  title: string;
  content: string;
  defaultOpen: boolean;
}

const THINKING_HEADINGS = [
  '## 🔍 推理链',
  '## ❓ 自我追问',
  '## 💡 最终结论',
] as const;

function parseThinkingSections(text: string): Section[] | null {
  const hasAny = THINKING_HEADINGS.some(h => text.includes(h));
  if (!hasAny) return null;

  const sections: Section[] = [];
  let remaining = text;

  for (let i = 0; i < THINKING_HEADINGS.length; i++) {
    const heading = THINKING_HEADINGS[i]!;
    const idx = remaining.indexOf(heading);
    if (idx === -1) continue;

    const afterHeading = remaining.slice(idx + heading.length);
    const nextIdx = THINKING_HEADINGS.slice(i + 1).reduce((min, h) => {
      const pos = afterHeading.indexOf(h);
      return pos !== -1 && pos < min ? pos : min;
    }, afterHeading.length);

    sections.push({
      title: heading.replace('## ', ''),
      content: afterHeading.slice(0, nextIdx).trim(),
      defaultOpen: heading === '## 💡 最终结论',
    });
  }

  return sections.length > 0 ? sections : null;
}

function SectionCard({ title, content, defaultOpen }: Section) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={styles.card}>
      <button className={styles.trigger} onClick={() => setOpen(o => !o)}>
        <span className={styles.title}>{title}</span>
        <Icon
          name="chevron"
          size={11}
          className={`${styles.chevron}${open ? ` ${styles.chevronOpen}` : ''}`}
        />
      </button>
      <div className={`${styles.expandWrapper}${open ? ` ${styles.open}` : ''}`}>
        <div className={styles.expandInner}>
          <div className={styles.content}>
            <ContentRenderer content={content} />
          </div>
        </div>
      </div>
    </div>
  );
}

interface ThinkingModeRendererProps {
  content: string;
  className?: string;
}

export function ThinkingModeRenderer({ content, className }: ThinkingModeRendererProps) {
  const sections = parseThinkingSections(content);

  if (!sections) {
    // Not a thinking-mode response, fall through to caller
    return null;
  }

  return (
    <div className={`${styles.container}${className ? ` ${className}` : ''}`}>
      {sections.map((section, i) => (
        <SectionCard key={i} {...section} />
      ))}
    </div>
  );
}

export { parseThinkingSections };
