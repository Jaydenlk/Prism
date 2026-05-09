import { useMemo } from 'react';
import { marked } from 'marked';
import type { ContentBlock } from '@/api/types';
import { Badge } from '@/components/Badge/Badge';
import styles from './MessageBubble.module.css';

interface ToolState {
  id: string;
  name: string;
  status: 'running' | 'ok' | 'error';
}

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  contentBlocks?: ContentBlock[];
  streamingTools?: ToolState[];
  isStreaming?: boolean;
}

function renderMarkdown(text: string): string {
  try {
    return marked.parse(text, { async: false }) as string;
  } catch {
    return text;
  }
}

export function MessageBubble({
  role,
  content,
  contentBlocks,
  streamingTools,
  isStreaming,
}: MessageBubbleProps) {
  const html = useMemo(() => {
    if (role === 'assistant' && content) return renderMarkdown(content);
    return '';
  }, [role, content]);

  const thinkingBlocks = contentBlocks?.filter(b => b.type === 'thinking') ?? [];

  if (role === 'user') {
    return (
      <div className={`${styles.wrap} ${styles.userWrap}`}>
        <div className={styles.userBubble}>{content}</div>
      </div>
    );
  }

  // Assistant
  const tools = streamingTools ?? [];

  return (
    <div className={`${styles.wrap} ${styles.assistantWrap}`}>
      {thinkingBlocks.map((b, i) => (
        <div key={i} className={styles.thinkingText}>
          [思考] {String(b.thinking ?? '').slice(0, 120)}
        </div>
      ))}
      {tools.map(tool => (
        <div
          key={tool.id}
          className={`${styles.toolCard} ${
            tool.status === 'running'
              ? styles.toolCardRunning
              : tool.status === 'ok'
              ? styles.toolCardOk
              : styles.toolCardError
          }`}
        >
          <Badge variant={tool.status === 'running' ? 'amber' : tool.status === 'ok' ? 'teal' : 'rust'}>
            {tool.status === 'running' ? '运行中' : tool.status === 'ok' ? '完成' : '失败'}
          </Badge>
          <span>{tool.name}</span>
        </div>
      ))}
      {content ? (
        <div
          className={styles.assistantBubble}
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : isStreaming ? (
        <div className={styles.assistantBubble}>
          <span className={styles.cursor} />
        </div>
      ) : null}
    </div>
  );
}

export type { ToolState };
