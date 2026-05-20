import { useRef, useEffect } from 'react';
import { Icon } from '@/components/Icon/Icon';
import styles from './Composer.module.css';

export type ChatMode = 'normal' | 'thinking' | 'think_tank';

interface ComposerProps {
  onSend: (text: string) => void;
  onStop: () => void;
  isRunning: boolean;
  disabled?: boolean;
  mode?: ChatMode;
  onModeChange?: (mode: ChatMode) => void;
}

export function Composer({ onSend, onStop, isRunning, disabled, mode = 'normal', onModeChange }: ComposerProps) {
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
      {onModeChange && (
        <div className={styles.modeBar}>
          <button
            className={`${styles.modeBtn} ${mode === 'normal' ? styles.modeBtnActive : ''}`}
            onClick={() => onModeChange('normal')}
            disabled={isRunning}
            title="普通模式"
          >
            普通
          </button>
          <button
            className={`${styles.modeBtn} ${mode === 'thinking' ? styles.modeBtnActive : ''}`}
            onClick={() => onModeChange('thinking')}
            disabled={isRunning}
            title="深度思考模式"
          >
            深度思考
          </button>
          <button
            className={`${styles.modeBtn} ${mode === 'think_tank' ? styles.modeBtnActive : ''}`}
            onClick={() => onModeChange('think_tank')}
            disabled={isRunning}
            title="智囊团模式"
          >
            智囊团
          </button>
        </div>
      )}
      <div className={styles.inputRow}>
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
    </div>
  );
}
