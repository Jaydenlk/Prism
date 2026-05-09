import { useRef, useEffect, useCallback } from 'react';
import type { Message } from '@/api/types';
import { PrismMark } from '@/components/Icon/Icon';
import { EmptyState } from './EmptyState';
import { MessageBubble } from './MessageBubble';
import type { ToolState } from './MessageBubble';
import styles from './MessageList.module.css';

interface MessageListProps {
  messages: Message[];
  streamingContent: string;
  streamingTools: ToolState[];
  isRunning: boolean;
  onSelectExample: (text: string) => void;
}

function extractText(msg: Message): string {
  return msg.content
    .filter(b => b.type === 'text')
    .map(b => b.text ?? '')
    .join('\n');
}

export function MessageList({
  messages,
  streamingContent,
  streamingTools,
  isRunning,
  onSelectExample,
}: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);

  const scrollToBottom = useCallback(() => {
    if (!userScrolledUp.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, scrollToBottom]);

  function handleScroll() {
    const el = listRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    userScrolledUp.current = distFromBottom > 100;
  }

  const isEmpty = messages.length === 0 && !isRunning && !streamingContent;

  return (
    <div className={styles.list} ref={listRef} onScroll={handleScroll}>
      {isEmpty ? (
        <EmptyState onSelectExample={onSelectExample} />
      ) : (
        <>
          {messages.map(msg => {
            const role = msg.role === 'user' ? 'user' : 'assistant';
            const text = extractText(msg);
            return (
              <MessageBubble
                key={msg.id}
                role={role}
                content={text || msg.text_preview || ''}
                contentBlocks={msg.content}
              />
            );
          })}
          {streamingContent || streamingTools.length > 0 ? (
            <MessageBubble
              role="assistant"
              content={streamingContent}
              streamingTools={streamingTools}
              isStreaming
            />
          ) : isRunning ? (
            <div className={styles.thinkingRow}>
              <PrismMark size={14} />
              <span>Agent 在思考…</span>
            </div>
          ) : null}
        </>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
