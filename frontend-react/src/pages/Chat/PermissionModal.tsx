import { useState, useEffect, useCallback } from 'react';
import { Modal } from '@/components/Modal/Modal';
import { Button } from '@/components/Button/Button';
import { Icon } from '@/components/Icon/Icon';
import { Badge } from '@/components/Badge/Badge';
import * as api from '@/api/client';
import styles from './PermissionModal.module.css';

export interface PermissionRequest {
  request_id: string;
  tool_name: string;
  description: string;
  input_preview?: string;
}

interface PermissionModalProps {
  request: PermissionRequest;
  sessionId: string;
  onResolved: () => void;
}

const TIMEOUT_SECONDS = 300;

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function PermissionModal({ request, sessionId, onResolved }: PermissionModalProps) {
  const [secondsLeft, setSecondsLeft] = useState(TIMEOUT_SECONDS);
  const [submitting, setSubmitting] = useState(false);

  const handleDecision = useCallback(async (decision: 'allow' | 'deny') => {
    if (submitting) return;
    setSubmitting(true);
    try {
      await api.sessions.permissionAnswer(sessionId, {
        request_id: request.request_id,
        decision,
      });
    } catch { /* best-effort */ }
    onResolved();
  }, [submitting, sessionId, request.request_id, onResolved]);

  // Reset state when request changes
  useEffect(() => {
    setSecondsLeft(TIMEOUT_SECONDS);
    setSubmitting(false);
  }, [request.request_id]);

  // Countdown timer
  useEffect(() => {
    if (submitting) return;

    const id = setInterval(() => {
      setSecondsLeft(prev => {
        if (prev <= 1) {
          clearInterval(id);
          handleDecision('deny');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(id);
  }, [request.request_id, submitting, handleDecision]);

  function handleClose() {
    handleDecision('deny');
  }

  return (
    <Modal open onClose={handleClose} width={480}>
      <div className={styles.content}>
        <h3 className={styles.title}>这一步需要你点头</h3>
        <p className={styles.subtitle}>Agent 想运行一个可能改动系统的操作，请确认。</p>

        <div className={styles.toolRow}>
          <Icon name="terminal" size={15} />
          <Badge variant="amber">{request.tool_name}</Badge>
        </div>

        {request.input_preview && (
          <pre className={styles.inputPreview}>{request.input_preview}</pre>
        )}

        <p className={styles.description}>{request.description}</p>

        <div
          className={styles.timer}
          style={{ color: secondsLeft < 60 ? 'var(--danger)' : 'var(--ink-3)' }}
        >
          {formatTime(secondsLeft)}
        </div>

        <div className={styles.actions}>
          <Button
            variant="danger"
            disabled={submitting}
            onClick={() => handleDecision('deny')}
          >
            拒绝
          </Button>
          <Button
            variant="primary"
            disabled={submitting}
            loading={submitting}
            onClick={() => handleDecision('allow')}
          >
            允许
          </Button>
        </div>
      </div>
    </Modal>
  );
}
