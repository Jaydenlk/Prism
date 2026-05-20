import { useMemo } from 'react';
import { ContentRenderer } from './ContentRenderer';
import styles from './ThinkTankMessage.module.css';

interface PersonaSection {
  name: string;
  isSummary: boolean;
  content: string;
}

function parseThinkTankContent(text: string): PersonaSection[] {
  // Split on ### 🧠 {name} and ### 📋 综合分析
  const lines = text.split('\n');
  const sections: PersonaSection[] = [];
  let current: PersonaSection | null = null;
  const contentLines: string[] = [];

  function flush() {
    if (current) {
      current.content = contentLines.join('\n').trim();
      sections.push(current);
      contentLines.length = 0;
    }
  }

  for (const line of lines) {
    const personaMatch = line.match(/^###\s*🧠\s*(.+)$/);
    const summaryMatch = line.match(/^###\s*📋\s*(.+)$/);

    if (personaMatch && personaMatch[1]) {
      flush();
      current = { name: personaMatch[1].trim(), isSummary: false, content: '' };
    } else if (summaryMatch && summaryMatch[1]) {
      flush();
      current = { name: summaryMatch[1].trim(), isSummary: true, content: '' };
    } else {
      contentLines.push(line);
    }
  }
  flush();

  return sections;
}

interface ThinkTankMessageProps {
  content: string;
}

export function ThinkTankMessage({ content }: ThinkTankMessageProps) {
  const sections = useMemo(() => parseThinkTankContent(content), [content]);

  if (sections.length === 0) {
    return <ContentRenderer content={content} />;
  }

  return (
    <div className={styles.container}>
      {sections.map((section, i) => (
        <div
          key={i}
          className={`${styles.card} ${section.isSummary ? styles.summaryCard : styles.personaCard}`}
        >
          <div className={`${styles.cardHeader} ${section.isSummary ? styles.summaryHeader : ''}`}>
            <span className={styles.cardIcon}>{section.isSummary ? '📋' : '🧠'}</span>
            <span className={styles.cardName}>{section.name}</span>
          </div>
          <div className={styles.cardBody}>
            <ContentRenderer content={section.content} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function isThinkTankResponse(content: string): boolean {
  return /^###\s*🧠\s*.+$/m.test(content) || /^###\s*📋\s*.+$/m.test(content);
}
