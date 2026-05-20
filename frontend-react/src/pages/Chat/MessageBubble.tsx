import { useRef, memo } from 'react';
import type { ContentBlock } from '@/api/types';
import { useToast } from '@/components/Toast/ToastContext';
import { Icon } from '@/components/Icon/Icon';
import { ContentRenderer } from './ContentRenderer';
import { ToolCard } from './ToolCard';
import { ThinkingBlock } from './ThinkingBlock';
import { ThinkTankMessage, isThinkTankResponse } from './ThinkTankMessage';
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
  confidence?: 'high' | 'medium' | 'low';
  uncertainClaims?: string[];
}

function MessageBubbleInner({
  role,
  content,
  contentBlocks,
  streamingTools,
  isStreaming,
  confidence,
  uncertainClaims,
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
                if (!text) return null;
                return isThinkTankResponse(text) ? (
                  <ThinkTankMessage key={i} content={text} />
                ) : (
                  <ContentRenderer key={i} content={text} className={styles.assistantBubble} />
                );
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
              isThinkTankResponse(content) ? (
                <ThinkTankMessage content={content} />
              ) : (
                <ContentRenderer content={content} className={styles.assistantBubble} />
              )
            ) : isStreaming ? (
              <div className={styles.assistantBubble}>
                <span className={styles.cursor} />
              </div>
            ) : null}
          </>
        )}
      </div>

      {role === 'assistant' && !isStreaming && confidence && confidence !== 'high' && (
        <div>
          {confidence === 'medium' && (
            <span style={{ display: 'inline-block', background: '#FEF3CD', color: '#856404', borderRadius: 4, padding: '4px 8px', fontSize: 12, marginTop: 6 }}>
              ⚠ 部分内容待确认
            </span>
          )}
          {confidence === 'low' && (
            <div style={{ marginTop: 6 }}>
              <span style={{ display: 'inline-block', background: '#F8D7DA', color: '#721C24', borderRadius: 4, padding: '4px 8px', fontSize: 12 }}>
                ❓ 置信度较低，建议确认
              </span>
              {uncertainClaims && uncertainClaims.length > 0 && (
                <ul style={{ margin: '4px 0 0 0', paddingLeft: 16, fontSize: 12, color: '#721C24' }}>
                  {uncertainClaims.map((claim, i) => (
                    <li key={i}>{claim}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

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
