import { useState, useEffect, useRef } from 'react';
import * as api from '@/api/client';
import type { Memory } from '@/api/types';
import { Button } from '@/components/Button/Button';
import styles from './SettingsPage.module.css';

export function MemoryTab() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [addContent, setAddContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await api.listMemories();
        if (!cancelled) setMemories(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  function handleSearchChange(value: string) {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setError(null);
      try {
        const data = value.trim()
          ? await api.searchMemories(value.trim())
          : await api.listMemories();
        setMemories(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : '搜索失败');
      }
    }, 300);
  }

  async function handleAdd() {
    if (!addContent.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await api.addMemory(addContent.trim());
      setMemories((prev) => [created, ...prev]);
      setAddContent('');
      setAddOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string, preview: string) {
    if (!window.confirm(`确认删除记忆？\n\n"${preview.slice(0, 60)}${preview.length > 60 ? '…' : ''}"`)) return;
    setDeletingId(id);
    setError(null);
    try {
      await api.deleteMemory(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className={styles.section}>
      <div className={styles.rowHeader}>
        <span className={styles.rowHeaderTitle}>AI 记忆</span>
        <Button size="sm" icon="plus" onClick={() => setAddOpen(true)}>添加记忆</Button>
      </div>

      <div className={styles.field} style={{ marginBottom: 20 }}>
        <input
          className={styles.input}
          placeholder="搜索记忆..."
          value={searchQuery}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
      </div>

      {addOpen && (
        <div className={styles.field} style={{ marginBottom: 20 }}>
          <textarea
            className={styles.input}
            style={{ height: 'auto', minHeight: 80, padding: '10px 14px', resize: 'vertical' }}
            placeholder="输入要记住的内容..."
            value={addContent}
            onChange={(e) => setAddContent(e.target.value)}
            autoFocus
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setAddOpen(false); setAddContent(''); }}
            >
              取消
            </Button>
            <Button size="sm" loading={saving} onClick={handleAdd}>保存</Button>
          </div>
        </div>
      )}

      {error && (
        <div style={{ color: 'var(--danger)', fontSize: 13, marginBottom: 16 }}>{error}</div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--ink-3)' }}>加载中...</div>
      ) : memories.length === 0 ? (
        <div className={styles.emptyState}>
          AI 还没有关于你的记忆。聊天后会自动记住重要信息。
        </div>
      ) : (
        <div className={styles.cardGrid}>
          {memories.map((m) => (
            <div key={m.id} className={styles.card}>
              <div className={styles.cardBody}>
                <div style={{ fontSize: 14, color: 'var(--ink)', lineHeight: 1.5 }}>{m.memory}</div>
                {m.created_at && (
                  <div className={styles.cardMeta} style={{ marginTop: 6, marginBottom: 0 }}>
                    {new Date(m.created_at).toLocaleString('zh-CN', {
                      year: 'numeric', month: '2-digit', day: '2-digit',
                      hour: '2-digit', minute: '2-digit',
                    })}
                  </div>
                )}
              </div>
              <div className={styles.cardActions}>
                <Button
                  size="sm"
                  variant="danger"
                  loading={deletingId === m.id}
                  onClick={() => handleDelete(m.id, m.memory)}
                >
                  删除
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
