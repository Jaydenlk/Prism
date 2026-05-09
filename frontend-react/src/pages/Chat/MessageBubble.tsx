import type { ContentBlock } from '@/api/types';
import { ContentRenderer } from './ContentRenderer';
import { ToolCard } from './ToolCard';
import { ThinkingBlock } from './ThinkingBlock';
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

export function MessageBubble({
  role,
  content,
  contentBlocks,
  streamingTools,
  isStreaming,
}: MessageBubbleProps) {
  if (role === 'user') {
    return (
      <div className={`${styles.wrap} ${styles.userWrap}`}>
        <div className={styles.userBubble}>{content}</div>
      </div>
    );
  }

  // Assistant: prefer contentBlocks (final messages) over raw string
  const hasBlocks = contentBlocks && contentBlocks.length > 0;

  return (
    <div className={`${styles.wrap} ${styles.assistantWrap}`}>
      {hasBlocks ? (
        <>
          {contentBlocks.map((block, i) => {
            if (block.type === 'thinking') {
              return (
                <ThinkingBlock
                  key={i}
                  content={String(block.thinking ?? '')}
                />
              );
            }
            if (block.type === 'tool_use') {
              return (
                <ToolCard
                  key={i}
                  name={String(block.name ?? 'tool')}
                  status="ok"
                  input={block.input ? JSON.stringify(block.input, null, 2) : undefined}
                />
              );
            }
            if (block.type === 'text') {
              const text = String(block.text ?? '');
              return text ? (
                <ContentRenderer key={i} content={text} className={styles.assistantBubble} />
              ) : null;
            }
            return null;
          })}
        </>
      ) : (
        <>
          {/* Streaming path: render tools from state, text as ContentRenderer */}
          {(streamingTools ?? []).map(tool => (
            <ToolCard
              key={tool.id}
              name={tool.name}
              status={tool.status}
            />
          ))}
          {content ? (
            <ContentRenderer content={content} className={styles.assistantBubble} />
          ) : isStreaming ? (
            <div className={styles.assistantBubble}>
              <span className={styles.cursor} />
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export type { ToolState };
