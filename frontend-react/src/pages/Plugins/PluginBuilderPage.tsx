import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import { Button } from '@/components/Button/Button';
import { Badge } from '@/components/Badge/Badge';
import { Spinner } from '@/components/Spinner/Spinner';
import { ConfirmModal } from '@/components/ConfirmModal/ConfirmModal';
import { useToast } from '@/components/Toast/ToastContext';
import { useSSE } from '@/hooks/useSSE';
import * as api from '@/api/client';
import type { PluginLibraryItem, SSEEvent } from '@/api/types';
import { renderMarkdown } from '@/utils/markdown';
import styles from './PluginBuilderPage.module.css';

// ── Types ──────────────────────────────────────────────────────────────────

interface BuilderMessage {
  role: 'user' | 'agent';
  content: string;
  at: string;
  streaming?: boolean;
  _streamId?: string;
}

interface ConsentData {
  name: string;
  type: string;
  permissions: {
    allowed_tools?: string[];
    allowed_models?: string[];
    storage_scope?: string;
    network_access?: boolean;
  };
  yaml: string;
  description: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function nowTime(): string {
  return new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

function parseConsentFromText(text: string): Partial<ConsentData> {
  const yamlMatch = text.match(/```ya?ml\s*([\s\S]*?)```/i);
  const yaml = (yamlMatch?.[1] ?? text).trim();

  let type = 'tool';
  const typeMatch = yaml.match(/^\s*type:\s*([a-z_]+)/mi);
  if (typeMatch?.[1]) type = typeMatch[1];

  const permissions: ConsentData['permissions'] = {};
  const permBlock = yaml.match(/^\s*permissions:\s*\n([\s\S]*?)(?=^\S|$)/mi);
  if (permBlock?.[1]) {
    const block = permBlock[1];
    const g = (key: string): string | null => {
      const m = block.match(new RegExp('^\\s{2,}' + key + ':\\s*(.*)$', 'mi'));
      return m?.[1]?.trim() ?? null;
    };
    const at = g('allowed_tools');
    const am = g('allowed_models');
    const ss = g('storage_scope');
    const na = g('network_access');
    if (at) permissions.allowed_tools = at.replace(/^\[|\]$/g, '').split(',').map(s => s.trim()).filter(Boolean);
    if (am) permissions.allowed_models = am.replace(/^\[|\]$/g, '').split(',').map(s => s.trim()).filter(Boolean);
    if (ss) permissions.storage_scope = ss;
    if (na) permissions.network_access = /true|yes/i.test(na);
  }

  return { type, permissions, yaml };
}

// ── Component ──────────────────────────────────────────────────────────────

export function PluginBuilderPage() {
  const { addToast } = useToast();

  // Builder conversation state
  const [msgs, setMsgs]                         = useState<BuilderMessage[]>([]);
  const [sessionId, setSessionId]               = useState<string | null>(null);
  const [running, setRunning]                   = useState(false);
  const [progress, setProgress]                 = useState(0);
  const [inputText, setInputText]               = useState('');

  // Consent modal
  const [consent, setConsent]                   = useState<ConsentData | null>(null);

  // Save modal
  const [saveOpen, setSaveOpen]                 = useState(false);
  const [saveName, setSaveName]                 = useState('');
  const [saveDesc, setSaveDesc]                 = useState('');
  const [saveYaml, setSaveYaml]                 = useState('');
  const [saving, setSaving]                     = useState(false);

  // View manifest modal
  const [viewManifest, setViewManifest]         = useState<{ name: string; yaml: string } | null>(null);

  // Library state
  const [library, setLibrary]                   = useState<PluginLibraryItem[]>([]);
  const [libraryLoading, setLibraryLoading]     = useState(false);
  const [actionLoading, setActionLoading]       = useState<string | null>(null);
  const [confirmDeletePlugin, setConfirmDeletePlugin] = useState<PluginLibraryItem | null>(null);

  const bottomRef  = useRef<HTMLDivElement>(null);
  const streamBuf  = useRef<Record<string, { text: string; finalized: boolean }>>({});
  const rafHandle  = useRef<number | null>(null);

  // ── Library ──────────────────────────────────────────────────────────────
  async function loadLibrary() {
    setLibraryLoading(true);
    try {
      const data = await api.plugins.listLibrary();
      setLibrary(Array.isArray(data) ? data : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      addToast(msg, 'error');
    }
    setLibraryLoading(false);
  }

  useEffect(() => { loadLibrary(); }, []);

  // ── SSE streaming ─────────────────────────────────────────────────────────
  function scheduleFlush() {
    if (rafHandle.current) return;
    rafHandle.current = requestAnimationFrame(() => {
      rafHandle.current = null;
      const buf = streamBuf.current;
      const ids = Object.keys(buf);
      if (!ids.length) return;
      setMsgs(prev => {
        const next = [...prev];
        for (const msgId of ids) {
          const entry = buf[msgId];
          if (!entry || entry.finalized) continue;
          const idx = next.findIndex(m => m._streamId === msgId);
          if (idx >= 0) {
            const existing = next[idx];
            if (existing) next[idx] = { ...existing, content: entry.text || '…', streaming: true };
          } else {
            next.push({ _streamId: msgId, role: 'agent' as const, at: 'now', content: entry.text || '…', streaming: true });
          }
        }
        return next;
      });
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  const handleSSEEvent = useCallback((evt: SSEEvent) => {
    switch (evt.type) {
      case 'text_delta': {
        const mid = (evt.message_id as string) || 'default';
        if (!streamBuf.current[mid]) streamBuf.current[mid] = { text: '', finalized: false };
        streamBuf.current[mid].text += (evt.text as string) || '';
        scheduleFlush();
        break;
      }
      case 'message_complete': {
        const blocks = Array.isArray(evt.content) ? evt.content as Array<{ type: string; text?: string }> : [];
        const text = blocks.filter(b => b.type === 'text').map(b => b.text ?? '').join('\n');
        setMsgs(prev => {
          const next = prev.filter(m => !m.streaming);
          next.push({ role: 'agent', at: nowTime(), content: text || '…', streaming: false });
          return next;
        });
        for (const k of Object.keys(streamBuf.current)) { const e = streamBuf.current[k]; if (e) e.finalized = true; }
        streamBuf.current = {};
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
        break;
      }
      case 'harness_event': {
        if (evt.subtype === 'step') {
          const pct = typeof evt.completion_pct === 'number' ? evt.completion_pct : null;
          if (pct !== null) setProgress(Math.round(pct));
        }
        if (evt.subtype === 'plugin_manifest_ready') {
          const data = evt.data as Record<string, unknown> || {};
          const manifestName = (data.name as string) || 'my-plugin';
          const manifestDesc = (data.description as string) || '';
          const manifestYaml = (data.manifest_yaml as string) || '';
          const manifestJson = (data.manifest_json as Record<string, unknown>) || {};
          setSaveName(manifestName);
          setSaveDesc(manifestDesc);
          setSaveYaml(manifestYaml);
          setConsent({
            name: manifestName,
            type: (manifestJson.type as string) || 'tool',
            permissions: (manifestJson.permissions as ConsentData['permissions']) || {},
            yaml: manifestYaml,
            description: manifestDesc,
          });
        }
        break;
      }
      case 'run_complete':
      case 'run_crashed':
      case 'run_error':
        setRunning(false);
        break;
    }
  }, []);

  useSSE({ sessionId, onEvent: handleSSEEvent, enabled: running });

  // ── Send message ──────────────────────────────────────────────────────────
  async function handleSend() {
    const text = inputText.trim();
    if (!text || running) return;
    setInputText('');

    setMsgs(prev => [...prev, { role: 'user', at: nowTime(), content: text }]);
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });

    try {
      let sid = sessionId;
      if (!sid) {
        const sess = await api.sessions.create({ title: 'Plugin Builder' });
        sid = sess.id;
        setSessionId(sid);
        setProgress(0);
        streamBuf.current = {};
      }

      await api.tasks.submit({ session_id: sid, prompt: text, agent_type: 'plugin_builder' });
      setRunning(true);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '发送失败';
      addToast(msg, 'error');
      setRunning(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  function handleReset() {
    if (rafHandle.current) cancelAnimationFrame(rafHandle.current);
    streamBuf.current = {};
    setSessionId(null);
    setMsgs([]);
    setProgress(0);
    setRunning(false);
  }

  // ── Manual "save" from last message ──────────────────────────────────────
  function openConsentFromLastMsg() {
    const last = [...msgs].reverse().find(m => m.role === 'agent' && !m.streaming);
    if (!last) return;
    const parsed = parseConsentFromText(last.content);
    setConsent({
      name: saveName || 'my-plugin',
      type: parsed.type || 'tool',
      permissions: parsed.permissions || {},
      yaml: parsed.yaml || last.content,
      description: saveDesc,
    });
  }

  // ── Library CRUD ──────────────────────────────────────────────────────────
  async function handleTogglePlugin(plugin: PluginLibraryItem) {
    setActionLoading(plugin.id);
    try {
      await api.plugins.patch(plugin.id, { enabled: !plugin.enabled });
      addToast(plugin.enabled ? `已禁用 ${plugin.name}` : `已启用 ${plugin.name}`, 'success');
      await loadLibrary();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '操作失败';
      addToast(msg, 'error');
    }
    setActionLoading(null);
  }

  async function handleDeletePlugin(plugin: PluginLibraryItem) {
    setConfirmDeletePlugin(plugin);
  }

  async function handleDeletePluginConfirm() {
    if (!confirmDeletePlugin) return;
    const plugin = confirmDeletePlugin;
    setConfirmDeletePlugin(null);
    setActionLoading(plugin.id);
    try {
      await api.plugins.delete(plugin.id);
      addToast(`已删除 ${plugin.name}`, 'success');
      await loadLibrary();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '删除失败';
      addToast(msg, 'error');
    }
    setActionLoading(null);
  }

  // ── Save to library ───────────────────────────────────────────────────────
  async function handleSaveToLibrary() {
    if (!saveName.trim()) { addToast('请填写插件名', 'error'); return; }
    setSaving(true);
    try {
      await api.plugins.save({
        name: saveName.trim(),
        version: '1.0.0',
        description: saveDesc.trim(),
        manifest_yaml: saveYaml,
      });
      addToast(`已保存到插件库 ${saveName.trim()}`, 'success');
      setSaveOpen(false);
      await loadLibrary();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败';
      addToast(msg, 'error');
    }
    setSaving(false);
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHead}>
        <h1 className={styles.pageTitle}>插件构建</h1>
        <p className={styles.pageSub}>
          与 Plugin Builder Agent 对话，自动构建 Plugin manifest；完成后一键保存到插件库。
        </p>
      </div>

      {/* Main two-pane layout */}
      <div className={styles.layout}>

        {/* ── Left pane: Conversational builder ─────────────────────────── */}
        <div className={styles.builderPane}>
          {/* Builder pane header */}
          <div className={styles.paneHeader}>
            <div className={styles.paneHeaderInfo}>
              <span className={styles.paneHeaderTitle}>Plugin Builder Agent</span>
              <span className={styles.paneHeaderSub}>
                {sessionId ? `session: ${sessionId.slice(-8)}` : '新对话'}
              </span>
            </div>
            {progress > 0 && (
              <div className={styles.progressRow}>
                <div className={styles.progressTrack}>
                  <div
                    className={styles.progressBar}
                    style={{
                      width: `${progress}%`,
                      background: progress >= 80 ? 'var(--teal)' : 'var(--amber)',
                    }}
                  />
                </div>
                <span className={styles.progressLabel}>{progress}%</span>
              </div>
            )}
            {sessionId && (
              <Button variant="ghost" size="sm" onClick={handleReset}>
                新建
              </Button>
            )}
          </div>

          {/* Messages */}
          <div className={styles.messages}>
            {msgs.length === 0 && !running ? (
              <div className={styles.emptyBuilder}>
                <div className={styles.emptyBuilderIcon}>
                  <Icon name="plugin" size={32} />
                </div>
                <p className={styles.emptyBuilderTitle}>Plugin Builder</p>
                <p className={styles.emptyBuilderSub}>描述你想要的插件，我来搜索现有方案或为你构建。</p>
                <p className={styles.emptyBuilderHint}>例如：「做一个能分析 PDF 文档的工具」</p>
              </div>
            ) : (
              <div className={styles.msgList}>
                {msgs.map((msg, i) => (
                  <div
                    key={i}
                    className={[styles.msgBubble, msg.role === 'user' ? styles.msgUser : styles.msgAgent].join(' ')}
                  >
                    <div
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content || '') }}
                    />
                    {msg.streaming && (
                      <span className={styles.cursor} />
                    )}
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          {/* Quick save button (visible when idle with messages) */}
          {msgs.length > 0 && !running && (
            <div className={styles.saveBarRow}>
              <button
                data-testid="plugin-open-consent"
                className={styles.saveBarBtn}
                onClick={openConsentFromLastMsg}
              >
                <Icon name="pin" size={12} />
                查看授权 &amp; 保存
              </button>
            </div>
          )}

          {/* Composer */}
          <div className={styles.composer}>
            <input
              data-testid="plugin-builder-input"
              className={styles.composerInput}
              type="text"
              placeholder="描述你想要的插件…"
              value={inputText}
              onChange={e => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={running}
            />
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleSend()}
              disabled={running || !inputText.trim()}
              loading={running}
            >
              {running ? '构建中' : '发送'}
            </Button>
          </div>
        </div>

        {/* ── Right pane: Plugin library ────────────────────────────────── */}
        <div className={styles.libraryPane}>
          <div className={styles.paneHeader}>
            <span className={styles.paneHeaderTitle}>插件库 ({library.length})</span>
            <Button variant="ghost" size="sm" onClick={loadLibrary} disabled={libraryLoading}>
              {libraryLoading ? <Spinner size={13} /> : '刷新'}
            </Button>
          </div>
          <div className={styles.libraryList}>
            {library.length === 0 && !libraryLoading && (
              <p className={styles.libraryEmpty}>
                暂无保存的插件。通过左侧对话构建 Plugin，完成后保存到这里。
              </p>
            )}
            {library.map(plugin => {
              const acting = actionLoading === plugin.id;
              return (
                <div key={plugin.id} className={[styles.pluginCard, plugin.enabled ? '' : styles.pluginCardDisabled].join(' ')}>
                  <div className={styles.pluginCardTop}>
                    <div className={styles.pluginCardInfo}>
                      <span className={styles.pluginName}>{plugin.name}</span>
                      <span className={styles.pluginVersion}>v{plugin.version}</span>
                    </div>
                    <Badge variant={plugin.enabled ? 'teal' : 'neutral'}>
                      {plugin.enabled ? '启用' : '禁用'}
                    </Badge>
                  </div>
                  {plugin.description && (
                    <p className={styles.pluginDesc}>{plugin.description}</p>
                  )}
                  <div className={styles.pluginActions}>
                    <button
                      className={styles.pluginActionBtn}
                      onClick={() => handleTogglePlugin(plugin)}
                      disabled={acting}
                    >
                      {plugin.enabled ? '禁用' : '启用'}
                    </button>
                    <button
                      className={styles.pluginActionBtn}
                      onClick={() => setViewManifest({ name: plugin.name, yaml: plugin.manifest_yaml || '' })}
                      disabled={acting}
                    >
                      Manifest
                    </button>
                    <button
                      className={[styles.pluginActionBtn, styles.pluginActionDanger].join(' ')}
                      onClick={() => handleDeletePlugin(plugin)}
                      disabled={acting}
                    >
                      {acting ? <Spinner size={12} /> : '删除'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Consent modal ──────────────────────────────────────────────────── */}
      {consent && (
        <div
          data-testid="plugin-consent-modal"
          className={styles.scrim}
          onClick={() => setConsent(null)}
        >
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <div className={styles.modalTitle}>授权 {consent.name || '插件'}</div>
              <div>
                <span
                  data-testid="plugin-consent-type-chip"
                  className={styles.typeChip}
                >
                  type: {consent.type}
                </span>
              </div>
            </div>

            <div data-testid="plugin-consent-permissions" className={styles.permissionsCard}>
              <p className={styles.permissionsNote}>此插件请求以下权限</p>
              {([
                ['允许调用的工具', (consent.permissions?.allowed_tools || []).join(', ') || '(无)'],
                ['允许使用的模型', (consent.permissions?.allowed_models || []).join(', ') || '(无)'],
                ['存储范围', consent.permissions?.storage_scope || 'session'],
                ['网络访问', consent.permissions?.network_access ? '允许' : '禁止'],
              ] as [string, string][]).map(([label, value]) => (
                <div key={label} className={styles.permissionRow}>
                  <span className={styles.permissionLabel}>{label}</span>
                  <span className={styles.permissionValue}>{value}</span>
                </div>
              ))}
            </div>

            <div className={styles.modalActions}>
              <Button
                data-testid="plugin-consent-allow"
                variant="primary"
                style={{ width: '100%', justifyContent: 'center', minHeight: 44 }}
                onClick={() => {
                  setSaveName(consent.name || saveName || 'my-plugin');
                  setSaveDesc(consent.description || saveDesc || '');
                  setSaveYaml(consent.yaml || saveYaml || '');
                  setConsent(null);
                  setSaveOpen(true);
                }}
              >
                允许并保存到插件库
              </Button>
              <Button
                data-testid="plugin-consent-cancel"
                variant="ghost"
                style={{ width: '100%', justifyContent: 'center', minHeight: 44 }}
                onClick={() => setConsent(null)}
              >
                取消
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Save modal ──────────────────────────────────────────────────────── */}
      {saveOpen && (
        <div
          data-testid="plugin-save-modal"
          className={styles.scrim}
          onClick={() => setSaveOpen(false)}
        >
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalTitle} style={{ fontSize: 16, marginBottom: 16 }}>保存到插件库</div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>插件名（唯一标识）</label>
              <input
                className={styles.formInput}
                value={saveName}
                onChange={e => setSaveName(e.target.value)}
                placeholder="my-plugin"
              />
            </div>
            <div className={styles.formGroup}>
              <label className={styles.formLabel}>描述</label>
              <input
                className={styles.formInput}
                value={saveDesc}
                onChange={e => setSaveDesc(e.target.value)}
                placeholder="插件功能简述…"
              />
            </div>
            <div className={styles.modalActions} style={{ flexDirection: 'row' }}>
              <Button
                variant="primary"
                onClick={() => void handleSaveToLibrary()}
                disabled={saving}
                loading={saving}
                style={{ flex: 1, justifyContent: 'center' }}
              >
                保存到插件库
              </Button>
              <Button variant="ghost" onClick={() => setSaveOpen(false)}>取消</Button>
            </div>
          </div>
        </div>
      )}

      {/* ── View manifest modal ─────────────────────────────────────────────── */}
      {viewManifest && (
        <div className={styles.scrim} onClick={() => setViewManifest(null)}>
          <div className={styles.modal} style={{ maxWidth: 560 }} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeaderRow}>
              <span className={styles.modalTitle}>{viewManifest.name} / manifest.yaml</span>
              <Button variant="ghost" size="sm" onClick={() => setViewManifest(null)}>关闭</Button>
            </div>
            <pre className={styles.yamlPre}>{viewManifest.yaml || '（manifest 为空）'}</pre>
          </div>
        </div>
      )}

      {/* ── Delete plugin confirm modal ─────────────────────────────────────── */}
      <ConfirmModal
        open={confirmDeletePlugin !== null}
        title="确认删除"
        message={confirmDeletePlugin ? `确认删除插件 "${confirmDeletePlugin.name}"？` : ''}
        confirmLabel="删除"
        danger
        loading={confirmDeletePlugin !== null && actionLoading === confirmDeletePlugin.id}
        onConfirm={handleDeletePluginConfirm}
        onCancel={() => setConfirmDeletePlugin(null)}
      />
    </div>
  );
}
