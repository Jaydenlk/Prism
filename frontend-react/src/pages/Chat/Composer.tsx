import { useRef, useEffect } from 'react';
import { Icon } from '@/components/Icon/Icon';
import styles from './Composer.module.css';

interface ComposerProps {
  onSend: (text: string) => void;
  onStop: () => void;
  isRunning: boolean;
  disabled?: boolean;
}

export function Composer({ onSend, onStop, isRunning, disabled }: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function autoGrow() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(200, el.scrollHeight) + 'px';
  }

  useEffect(() => {
    autoGrow();
  }, []);

  function submit() {
    const el = textareaRef.current;
    if (!el) return;
    const text = el.value.trim();
    if (!text || disabled || isRunning) return;
    onSend(text);
    el.value = '';
    el.style.height = 'auto';
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function handleInput() {
    autoGrow();
  }

  const canSend = !disabled && !isRunning;

  return (
    <div className={styles.container}>
      <textarea
        ref={textareaRef}
        className={styles.textarea}
        placeholder={isRunning ? '请稍等…' : '发送消息…'}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={disabled && !isRunning}
        rows={1}
      />
      {isRunning ? (
        <button className={styles.stopBtn} onClick={onStop} title="停止">
          <Icon name="close" size={14} />
        </button>
      ) : (
        <button
          className={styles.sendBtn}
          onClick={submit}
          disabled={!canSend}
          title="发送"
        >
          <Icon name="send" size={14} />
        </button>
      )}
    </div>
  );
}
