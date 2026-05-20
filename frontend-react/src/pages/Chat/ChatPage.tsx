import { useState, useEffect, useCallback } from 'react';
import { uuid } from '@/utils/cn';
import * as api from '@/api/client';
import type { Message, SSEEvent, ThinkTankConfig } from '@/api/types';
import { useSSE } from '@/hooks/useSSE';
import { useSessions } from '@/hooks/useSessions';
import { useToast } from '@/components/Toast/ToastContext';
import { PrismMark, PrismGlyph } from '@/components/Icon/Icon';
import { MessageList } from './MessageList';
import { Composer } from './Composer';
import type { ToolState } from './MessageBubble';
import { PermissionModal } from './PermissionModal';
import type { PermissionRequest } from './PermissionModal';
import { PlanPanel } from './PlanPanel';
import type { PlanStep } from './PlanPanel';
import { ThinkTankPanel } from './ThinkTankPanel';
import styles from './ChatPage.module.css';

function buildThinkTankPrompt(userText: string, config: ThinkTankConfig): string {
  const personaList = config.personas.map(p => `- ${p.name}`).join('\n');
  const modeDesc =
    config.mode === 'debate'
      ? '辩论式：每位 Persona 先独立发言，然后互相引用对方观点进行回应和反驳，最后综合分析。'
      : '德尔菲式：每位 Persona 先独立分析，汇总后形成共识与分歧，最后输出综合建议。';

  return `[智囊团模式]
讨论模式：${modeDesc}

请邀请以下 Persona 就用户问题展开多视角讨论：
${personaList}

输出格式要求：
- 每位 Persona 的发言使用 "### 🧠 {Persona名称}" 作为标题
- 综合分析使用 "### 📋 综合分析" 作为标题，包含共识、分歧和行动建议
- 每位 Persona 用第一人称，保持各自的思维风格和语气
${config.mode === 'debate' ? '- 辩论式：Persona 之间需要引用和回应彼此的观点' : '- 德尔菲式：最后综合分析要归纳所有 Persona 的核心观点'}

用户问题：
${userText}`;
}

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
  const [showThinkTankPanel, setShowThinkTankPanel] = useState(false);
  const [thinkTankConfig, setThinkTankConfig] = useState<ThinkTankConfig | null>(null);

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

        const msgs = Array.isArray(historyRes) ? historyRes : historyRes.items ?? [];
        setMessages(msgs);

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
          id: uuid(),
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

    // If think tank mode is active, wrap the prompt
    const effectivePrompt = thinkTankConfig
      ? buildThinkTankPrompt(text, thinkTankConfig)
      : text;

    // Optimistic user message — always show original text
    const userMsg: Message = {
      id: uuid(),
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
      const res = await api.tasks.submit({ session_id: sessionId, prompt: effectivePrompt });
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

  const isEmpty = !currentSessionId || (messages.length === 0 && !isRunning);

  if (isEmpty) {
    return (
      <div className={styles.page}>
        <div className={styles.welcomeLayout}>
          <div className={styles.welcomeContent}>
            <PrismGlyph size={48} />
            <h2 className={styles.welcomeTitle}>随便聊点什么。</h2>
            <p className={styles.welcomeSubtitle}>
              我会把你的问题分派给对的 Agent —— 研究、规划、执行或验证。
            </p>
          </div>
          <div className={styles.welcomeComposer}>
            <Composer
              onSend={handleSend}
              onStop={handleStop}
              isRunning={isRunning}
              thinkTankConfig={thinkTankConfig}
              onOpenThinkTank={() => setShowThinkTankPanel(true)}
            />
          </div>
          <div className={styles.welcomeExamples}>
            <span className={styles.welcomeExamplesLabel}>或者从这里开始</span>
            <div className={styles.welcomeExampleGrid}>
              {['读一下 executor/,帮我理解 TAOR 主循环是怎么转的',
                '上周的 runs 表现如何?哪里花钱最多?',
                '写一份 2026 年 Harness Engineering 的内部简报',
                '帮我搞一个只读 shell 的 Skill,就叫 readonly-shell',
              ].map((ex, i) => (
                <button
                  key={i}
                  className={styles.welcomeExampleBtn}
                  onClick={() => handleSend(ex)}
                  style={{ animationDelay: `${i * 80}ms` }}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>
        {showThinkTankPanel && (
          <ThinkTankPanel
            onConfirm={config => { setThinkTankConfig(config); setShowThinkTankPanel(false); }}
            onCancel={() => setShowThinkTankPanel(false)}
          />
        )}
      </div>
    );
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
        thinkTankConfig={thinkTankConfig}
        onOpenThinkTank={() => setShowThinkTankPanel(true)}
      />
      {showThinkTankPanel && (
        <ThinkTankPanel
          onConfirm={config => { setThinkTankConfig(config); setShowThinkTankPanel(false); }}
          onCancel={() => setShowThinkTankPanel(false)}
        />
      )}
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
