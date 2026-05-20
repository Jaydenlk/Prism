import { ContentRenderer } from './ContentRenderer';
import styles from './ThinkTankRenderer.module.css';

const PERSONA_PATTERN = /^### [🧠🔥💡🎯⚡🌊] (.+)$/;
const SYNTHESIS_PATTERN = /^### 📋 综合分析$/;

interface Section {
  type: 'persona' | 'synthesis';
  name: string;
  content: string;
}

export function parseThinkTankSections(text: string): Section[] | null {
  if (!text.includes('### 🧠') && !text.includes('### 🔥') && !text.includes('### 💡')) return null;

  const lines = text.split('\n');
  const sections: Section[] = [];
  let current: Section | null = null;

  for (const line of lines) {
    const synthMatch = line.match(SYNTHESIS_PATTERN);
    const personaMatch = line.match(PERSONA_PATTERN);

    if (synthMatch) {
      if (current) sections.push(current);
      current = { type: 'synthesis', name: '综合分析', content: '' };
    } else if (personaMatch) {
      if (current) sections.push(current);
      current = { type: 'persona', name: personaMatch[1] ?? '', content: '' };
    } else if (current) {
      current.content += line + '\n';
    }
  }
  if (current) sections.push(current);

  return sections.length > 0 ? sections : null;
}

interface ThinkTankRendererProps {
  content: string;
  className?: string;
}

export function ThinkTankRenderer({ content, className }: ThinkTankRendererProps) {
  const sections = parseThinkTankSections(content);
  if (!sections) return <ContentRenderer content={content} />;

  return (
    <div className={`${styles.container} ${className ?? ''}`}>
      {sections.map((section, i) => (
        <div key={i} className={section.type === 'synthesis' ? styles.synthesisCard : styles.personaCard}>
          <div className={styles.cardHeader}>
            <span className={styles.cardIcon}>{section.type === 'synthesis' ? '📋' : '🧠'}</span>
            <span className={styles.cardName}>{section.name}</span>
          </div>
          <div className={styles.cardBody}>
            <ContentRenderer content={section.content.trim()} />
          </div>
        </div>
      ))}
    </div>
  );
}
