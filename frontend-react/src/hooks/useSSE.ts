import { useEffect, useRef, useCallback, useState } from 'react';
import { openStream } from '@/api/client';
import type { SSEEvent } from '@/api/types';

type SSEStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

interface UseSSEOptions {
  sessionId: string | null;
  onEvent: (event: SSEEvent) => void;
  enabled?: boolean;
}

export function useSSE({ sessionId, onEvent, enabled = true }: UseSSEOptions) {
  const [status, setStatus] = useState<SSEStatus>('disconnected');
  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const disconnect = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  useEffect(() => {
    if (!sessionId || !enabled) {
      disconnect();
      return;
    }

    let cancelled = false;
    setStatus('connecting');

    openStream(sessionId, {
      onEvent: (evt) => {
        if (cancelled) return;
        setStatus('connected');
        onEventRef.current(evt);
      },
      onError: () => {
        if (cancelled) return;
        setStatus('error');
      },
      onClose: () => {
        if (cancelled) return;
        setStatus('disconnected');
      },
    }).then((es) => {
      if (cancelled) { es.close(); return; }
      esRef.current = es;
    }).catch(() => {
      if (!cancelled) setStatus('error');
    });

    return () => {
      cancelled = true;
      disconnect();
    };
  }, [sessionId, enabled, disconnect]);

  return { status, disconnect };
}
