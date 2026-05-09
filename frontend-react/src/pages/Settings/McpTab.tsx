import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import type { McpServer } from '@/api/types';
import { useToast } from '@/components/Toast/ToastContext';
import { Button } from '@/components/Button/Button';
import { Badge } from '@/components/Badge/Badge';
import { Modal } from '@/components/Modal/Modal';
import { ConfirmModal } from '@/components/ConfirmModal/ConfirmModal';
import { Spinner } from '@/components/Spinner/Spinner';
import styles from './SettingsPage.module.css';

interface McpFormState {
  name: string;
  transport: 'stdio' | 'http';
  command: string;
  url: string;
  description: string;
}

const EMPTY_FORM: McpFormState = {
  name: '',
  transport: 'stdio',
  command: '',
  url: '',
  description: '',
};

export function McpTab() {
  const { addToast } = useToast();
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [form, setForm] = useState<McpFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const list = await api.mcp.listServers();
        if (!cancelled) setServers(list);
      } catch (err) {
        if (!cancelled) addToast(err instanceof Error ? err.message : '加载失败', 'error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [addToast]);

  async function handleAdd() {
    if (!form.name) {
      addToast('请填写名称', 'error');
      return;
    }
    if (form.transport === 'stdio' && !form.command) {
      addToast('stdio 类型需要填写命令', 'error');
      return;
    }
    if (form.transport === 'http' && !form.url) {
      addToast('http 类型需要填写 URL', 'error');
      return;
    }
    setSaving(true);
    try {
      const created = await api.mcp.createServer({
        name: form.name,
        description: form.description || undefined,
        transport: form.transport,
        command: form.transport === 'stdio' ? form.command : undefined,
        url: form.transport === 'http' ? form.url : undefined,
      });
      setServers((prev) => [...prev, created]);
      addToast('MCP 服务已添加', 'success');
      setAddOpen(false);
      setForm(EMPTY_FORM);
    } catch (err) {
      addToast(err instanceof Error ? err.message : '添加失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await api.mcp.deleteServer(id);
      setServers((prev) => prev.filter((s) => s.id !== id));
      addToast('已删除', 'success');
    } catch (err) {
      addToast(err instanceof Error ? err.message : '删除失败', 'error');
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={20} />
      </div>
    );
  }

  return (
    <>
      <div className={styles.section}>
        <div className={styles.rowHeader}>
          <span className={styles.rowHeaderTitle}>MCP 服务器</span>
          <Button size="sm" icon="plus" onClick={() => setAddOpen(true)}>添加 MCP 服务</Button>
        </div>

        {servers.length === 0 ? (
          <div className={styles.emptyState}>暂无 MCP 服务，点击添加</div>
        ) : (
          <div className={styles.cardGrid}>
            {servers.map((s) => (
              <div key={s.id} className={styles.card}>
                <div className={styles.cardBody}>
                  <div className={styles.cardName}>{s.name}</div>
                  {s.description && <div className={styles.cardMeta}>{s.description}</div>}
                  <div className={styles.cardBadges}>
                    <Badge variant="neutral">{s.transport}</Badge>
                    {s.command && <Badge variant="neutral">{s.command}</Badge>}
                    {s.url && <Badge variant="teal">{s.url}</Badge>}
                  </div>
                </div>
                <div className={styles.cardActions}>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={deletingId === s.id}
                    onClick={() => setConfirmDeleteId(s.id)}
                  >
                    删除
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add MCP modal */}
      <Modal open={addOpen} onClose={() => { setAddOpen(false); setForm(EMPTY_FORM); }} title="添加 MCP 服务" width={480}>
        <div className={styles.modalFields}>
          <div className={styles.field}>
            <label className={styles.label}>名称 *</label>
            <input
              className={styles.input}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="my-mcp-server"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>描述</label>
            <input
              className={styles.input}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="可选说明"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>传输类型</label>
            <select
              className={styles.select}
              value={form.transport}
              onChange={(e) => setForm((f) => ({ ...f, transport: e.target.value as 'stdio' | 'http' }))}
            >
              <option value="stdio">stdio</option>
              <option value="http">http</option>
            </select>
          </div>
          {form.transport === 'stdio' ? (
            <div className={styles.field}>
              <label className={styles.label}>命令 *</label>
              <input
                className={styles.input}
                value={form.command}
                onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
                placeholder="npx my-mcp-server"
              />
            </div>
          ) : (
            <div className={styles.field}>
              <label className={styles.label}>URL *</label>
              <input
                className={styles.input}
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="http://localhost:3000"
              />
            </div>
          )}
        </div>
        <div className={styles.modalFooter}>
          <Button variant="ghost" onClick={() => { setAddOpen(false); setForm(EMPTY_FORM); }}>取消</Button>
          <Button loading={saving} onClick={handleAdd}>添加</Button>
        </div>
      </Modal>

      <ConfirmModal
        open={confirmDeleteId !== null}
        title="确认删除"
        message="确认删除该 MCP 服务？此操作不可撤销。"
        confirmLabel="删除"
        danger
        loading={deletingId !== null}
        onConfirm={() => { if (confirmDeleteId) handleDelete(confirmDeleteId); }}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </>
  );
}
