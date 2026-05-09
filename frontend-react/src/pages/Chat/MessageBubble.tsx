import { useRef, memo } from 'react';
import type { ContentBlock } from '@/api/types';
import { useToast } from '@/components/Toast/ToastContext';
import { Icon } from '@/components/Icon/Icon';
import { ContentRenderer } from './ContentRenderer';
import { ToolCard } from './ToolCard';
import { ThinkingBlock } from './ThinkingBlock';
import { htmlToMarkdown, copyToClipboard } from '@/utils/export';
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

function MessageBubbleInner({
  role,
  content,
  contentBlocks,
  streamingTools,
  isStreaming,
}: MessageBubbleProps) {
  const { addToast } = useToast();
  const contentRef = useRef<HTMLDivElement>(null);

  if (role === 'user') {
    return (
      <div className={`${styles.wrap} ${styles.userWrap}`}>
        <div className={styles.userBubble}>{content}</div>
      </div>
    );
  }

  async function handleCopyMarkdown() {
    const el = contentRef.current;
    if (!el) return;
    const markdown = htmlToMarkdown(el.innerHTML);
    try {
      await copyToClipboard(markdown);
      addToast('已复制', 'success');
    } catch {
      addToast('复制失败', 'error');
    }
  }

  // Assistant: prefer contentBlocks (final messages) over raw string
  const hasBlocks = contentBlocks && contentBlocks.length > 0;

  return (
    <div className={`${styles.wrap} ${styles.assistantWrap}`}>
      <div ref={contentRef}>
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

      {!isStreaming && (content || hasBlocks) && (
        <div className={styles.actionBar}>
          <button
            className={styles.actionBtn}
            onClick={handleCopyMarkdown}
            title="复制为 Markdown"
            aria-label="复制为 Markdown"
          >
            <Icon name="copy" size={13} />
          </button>
        </div>
      )}
    </div>
  );
}

export const MessageBubble = memo(MessageBubbleInner);

export type { ToolState };
