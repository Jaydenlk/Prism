import { useState, useEffect, useCallback } from 'react';
import { Modal } from '@/components/Modal/Modal';
import { Button } from '@/components/Button/Button';
import * as api from '@/api/client';
import styles from './QuestionModal.module.css';

export interface QuestionOption {
  label: string;
  description?: string;
}

export interface Question {
  question: string;
  header?: string;
  options?: QuestionOption[];
  multiSelect?: boolean;
}

export interface QuestionRequest {
  request_id: string;
  questions: Question[];
}

interface QuestionModalProps {
  request: QuestionRequest;
  sessionId: string;
  onResolved: () => void;
}

const TIMEOUT_SECONDS = 300;

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function QuestionModal({ request, sessionId, onResolved }: QuestionModalProps) {
  const [secondsLeft, setSecondsLeft] = useState(TIMEOUT_SECONDS);
  const [submitting, setSubmitting] = useState(false);
  // answers[questionIndex] = Set of selected labels or free-text string
  const [selectedOptions, setSelectedOptions] = useState<Map<number, Set<string>>>(() => new Map());
  const [otherTexts, setOtherTexts] = useState<Map<number, string>>(() => new Map());

  const handleSubmit = useCallback(async () => {
    if (submitting) return;
    setSubmitting(true);

    const answers: Record<string, unknown> = {};
    request.questions.forEach((q, idx) => {
      const selected = selectedOptions.get(idx) ?? new Set<string>();
      const otherText = otherTexts.get(idx) ?? '';
      const selectedArr = Array.from(selected);
      if (otherText.trim()) {
        selectedArr.push(otherText.trim());
      }
      answers[String(idx)] = {
        question: q.question,
        selected: selectedArr,
      };
    });

    try {
      await api.sessions.questionAnswer(sessionId, request.request_id, answers);
    } catch { /* best-effort */ }
    onResolved();
  }, [submitting, sessionId, request, selectedOptions, otherTexts, onResolved]);

  useEffect(() => {
    setSecondsLeft(TIMEOUT_SECONDS);
    setSubmitting(false);
    setSelectedOptions(new Map());
    setOtherTexts(new Map());
  }, [request.request_id]);

  useEffect(() => {
    if (submitting) return;

    const id = setInterval(() => {
      setSecondsLeft(prev => {
        if (prev <= 1) {
          clearInterval(id);
          handleSubmit();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(id);
  }, [request.request_id, submitting, handleSubmit]);

  function toggleOption(questionIdx: number, label: string, multiSelect: boolean) {
    setSelectedOptions(prev => {
      const next = new Map(prev);
      const current = new Set(next.get(questionIdx) ?? []);
      if (multiSelect) {
        if (current.has(label)) current.delete(label);
        else current.add(label);
      } else {
        if (current.has(label)) current.clear();
        else { current.clear(); current.add(label); }
      }
      next.set(questionIdx, current);
      return next;
    });
  }

  function setOtherText(questionIdx: number, text: string) {
    setOtherTexts(prev => {
      const next = new Map(prev);
      next.set(questionIdx, text);
      return next;
    });
  }

  return (
    <Modal open onClose={handleSubmit} width={520}>
      <div className={styles.content}>
        <h3 className={styles.title}>需要你的输入</h3>
        <p className={styles.subtitle}>请回答以下问题，帮助 Agent 继续执行。</p>

        {request.questions.map((q, idx) => {
          const selected = selectedOptions.get(idx) ?? new Set<string>();
          const otherText = otherTexts.get(idx) ?? '';
          const multiSelect = q.multiSelect ?? false;

          return (
            <div key={idx} className={styles.questionBlock}>
              {q.header && <div className={styles.questionHeader}>{q.header}</div>}
              <div className={styles.questionText}>{q.question}</div>

              {q.options && q.options.length > 0 && (
                <div className={styles.optionGrid}>
                  {q.options.map(opt => (
                    <button
                      key={opt.label}
                      className={`${styles.optionCard} ${selected.has(opt.label) ? styles.optionCardSelected : ''}`}
                      onClick={() => toggleOption(idx, opt.label, multiSelect)}
                      disabled={submitting}
                    >
                      <div className={styles.optionLabel}>{opt.label}</div>
                      {opt.description && (
                        <div className={styles.optionDesc}>{opt.description}</div>
                      )}
                    </button>
                  ))}
                </div>
              )}

              <div className={styles.otherRow}>
                <input
                  className={styles.otherInput}
                  type="text"
                  placeholder="其他（可选，自由填写）"
                  value={otherText}
                  onChange={e => setOtherText(idx, e.target.value)}
                  disabled={submitting}
                />
              </div>
            </div>
          );
        })}

        <div
          className={styles.timer}
          style={{ color: secondsLeft < 60 ? 'var(--danger)' : 'var(--ink-3)' }}
        >
          {formatTime(secondsLeft)}
        </div>

        <div className={styles.actions}>
          <Button
            variant="primary"
            disabled={submitting}
            loading={submitting}
            onClick={handleSubmit}
          >
            提交
          </Button>
        </div>
      </div>
    </Modal>
  );
}
