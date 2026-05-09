import { useState, useEffect, useCallback } from 'react';
import * as api from '@/api/client';
import type { Message, SSEEvent } from '@/api/types';
import { useSSE } from '@/hooks/useSSE';
import { useSessions } from '@/hooks/useSessions';
import { useToast } from '@/components/Toast/ToastContext';
import { PrismMark } from '@/components/Icon/Icon';
import { MessageList } from './MessageList';
import { Composer } from './Composer';
import type { ToolState } from './MessageBubble';
import { PermissionModal } from './PermissionModal';
import type { PermissionRequest } from './PermissionModal';
import { PlanPanel } from './PlanPanel';
import type { PlanStep } from './PlanPanel';
import styles from './ChatPage.module.css';

export function ChatPage() {
  const { currentSessionId, createSession, refreshSessions } = useSessions();
  const { addToast } = useToast();

  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [streamingTools, setStreamingTools] = useState<ToolState[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequest | null>(null);
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([]);
  const [planCurrentStep, setPlanCurrentStep] = useState(0);
  const [showPlan, setShowPlan] = useState(false);

  // Load messages when session changes
  useEffect(() => {
    if (!currentSessionId) {
      setMessages([]);
      setStreamingText('');
      setStreamingTools([]);
      setIsRunning(false);
      setLoadError(false);
      return;
    }

    let cancelled = false;
    const sid = currentSessionId;

    async function load() {
      setLoadingMessages(true);
      setLoadError(false);
      setMessages([]);
      setStreamingText('');
      setStreamingTools([]);

      try {
        const [meta, historyRes] = await Promise.all([
          api.sessions.get(sid),
          api.sessions.listMessages(sid, {}),
        ]);
        if (cancelled) return;

        setMessages(historyRes.items);

        // If session is already running, show running state
        if (meta.status === 'running' && meta.blocking_run_id) {
          setIsRunning(true);
        }
      } catch {
        if (!cancelled) setLoadError(true);
      } finally {
        if (!cancelled) setLoadingMessages(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [currentSessionId, retryKey]);

  // SSE event handler
  const handleSSEEvent = useCallback((evt: SSEEvent) => {
    const { type } = evt;

    switch (type) {
      case 'text_delta': {
        const delta = (evt.text as string | undefined) ?? (evt.delta as string | undefined) ?? '';
        setStreamingText(prev => prev + delta);
        break;
      }

      case 'tool_start': {
        const toolId = evt.tool_use_id as string;
        const toolName = (evt.tool_name as string | undefined) ?? 'tool';
        setStreamingTools(prev => [
          ...prev,
          { id: toolId, name: toolName, status: 'running' },
        ]);
        break;
      }

      case 'tool_end': {
        const toolId = evt.tool_use_id as string;
        const isError = !!(evt.is_error as boolean | undefined);
        setStreamingTools(prev =>
          prev.map(t =>
            t.id === toolId ? { ...t, status: isError ? 'error' : 'ok' } : t,
          ),
        );
        break;
      }

      case 'message_complete': {
        // Build final message from SSE payload
        const rawContent = (evt.content as Message['content'] | undefined) ?? [];
        const role = ((evt.role as string | undefined) ?? 'assistant') as Message['role'];

        const textPreview = rawContent
          .filter(b => b.type === 'text')
          .map(b => b.text ?? '')
          .join('\n');

        const finalMsg: Message = {
          id: crypto.randomUUID(),
          run_id: null,
          role,
          content: rawContent,
          text_preview: textPreview || null,
          sequence_no: 0,
          created_at: new Date().toISOString(),
        };

        // For user role messages from message_complete we skip — they're added optimistically
        if (role !== 'user') {
          setMessages(prev => {
            // Remove any streaming placeholders, add final message
            return [...prev, finalMsg];
          });
        }

        setStreamingText('');
        setStreamingTools([]);
        break;
      }

      case 'run_complete': {
        setIsRunning(false);
        setStreamingText('');
        setStreamingTools([]);
        refreshSessions();
        break;
      }

      case 'run_error': {
        setIsRunning(false);
        setStreamingText('');
        setStreamingTools([]);
        addToast((evt.error as string | undefined) ?? 'Run 失败', 'error');
        break;
      }

      case 'run_crashed': {
        setIsRunning(false);
        setStreamingText('');
        setStreamingTools([]);
        addToast((evt.reason as string | undefined) ?? 'Run 崩溃', 'error');
        break;
      }

      case 'permission_ask': {
        const reqId = evt.request_id as string | undefined;
        const toolName = evt.tool_name as string | undefined;
        const description = evt.description as string | undefined;
        const inputPreview = evt.input_preview as string | undefined;
        if (reqId && toolName && description) {
          setPermissionRequest({
            request_id: reqId,
            tool_name: toolName,
            description,
            input_preview: inputPreview,
          });
        }
        break;
      }

      case 'coordinator_plan_update': {
        const steps = evt.steps as PlanStep[] | undefined;
        const currentStep = evt.current_step as number | undefined;
        if (steps) {
          setPlanSteps(steps);
          setPlanCurrentStep(currentStep ?? 0);
          setShowPlan(true);
        }
        break;
      }

      case 'session_title': {
        refreshSessions();
        break;
      }

      case 'queue_update': {
        addToast('任务已排队', 'info');
        break;
      }

      default:
        break;
    }
  }, [currentSessionId, refreshSessions, addToast]);

  useSSE({
    sessionId: currentSessionId,
    onEvent: handleSSEEvent,
    enabled: !!currentSessionId,
  });

  async function handleSend(text: string) {
    let sessionId = currentSessionId;

    if (!sessionId) {
      try {
        const session = await createSession();
        sessionId = session.id;
      } catch {
        addToast('创建会话失败', 'error');
        return;
      }
    }

    // Optimistic user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      run_id: null,
      role: 'user',
      content: [{ type: 'text', text }],
      text_preview: text,
      sequence_no: 0,
      created_at: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMsg]);
    setIsRunning(true);
    setStreamingText('');
    setStreamingTools([]);

    try {
      const res = await api.tasks.submit({ session_id: sessionId, prompt: text });
      if (res.accepted_type === 'queued_query') {
        addToast(`任务已排队,第 ${res.queue_position ?? '?'} 位`, 'info');
        setIsRunning(false);
      }
    } catch (err) {
      addToast(err instanceof Error ? err.message : '发送失败', 'error');
      setMessages(prev => prev.filter(m => m.id !== userMsg.id));
      setIsRunning(false);
    }
  }

  async function handleStop() {
    if (!currentSessionId) return;
    try {
      const runs = await api.sessions.listRuns(currentSessionId);
      const activeRun = runs.find(r => r.status === 'running');
      if (activeRun) {
        await api.runs.cancel(activeRun.id, {});
      }
    } catch { /* best-effort */ }
    setIsRunning(false);
    setStreamingText('');
    setStreamingTools([]);
  }

  if (loadingMessages) {
    return (
      <div className={styles.page}>
        <div className={styles.loadingState}>
          <PrismMark size={18} />
          <span>正在加载会话…</span>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className={styles.page}>
        <div className={styles.errorState}>
          <div style={{ fontFamily: 'var(--serif)', fontStyle: 'italic' }}>
            加载失败,后端可能不可用
          </div>
          <button
            className={styles.retryBtn}
            onClick={() => setRetryKey(k => k + 1)}
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  function handleSelectExample(text: string) {
    handleSend(text);
  }

  return (
    <div className={styles.page}>
      <MessageList
        messages={messages}
        streamingContent={streamingText}
        streamingTools={streamingTools}
        isRunning={isRunning}
        onSelectExample={handleSelectExample}
      />
      <Composer
        onSend={handleSend}
        onStop={handleStop}
        isRunning={isRunning}
      />
      {showPlan && planSteps.length > 0 && (
        <PlanPanel
          steps={planSteps}
          currentStep={planCurrentStep}
          onClose={() => setShowPlan(false)}
        />
      )}
      {permissionRequest && currentSessionId && (
        <PermissionModal
          request={permissionRequest}
          sessionId={currentSessionId}
          onResolved={() => setPermissionRequest(null)}
        />
      )}
    </div>
  );
}
