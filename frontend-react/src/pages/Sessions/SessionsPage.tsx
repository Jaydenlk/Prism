import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '@/api/client';
import { useSessions } from '@/hooks/useSessions';
import { useToast } from '@/components/Toast/ToastContext';
import { groupByTime } from '@/utils/time';
import { downloadMarkdown } from '@/utils/export';
import { Icon } from '@/components/Icon/Icon';
import { Button } from '@/components/Button/Button';
import { Modal } from '@/components/Modal/Modal';
import { Badge } from '@/components/Badge/Badge';
import styles from './SessionsPage.module.css';

function formatTime(isoStr: string): string {
  const d = new Date(isoStr);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  if (d >= startOfToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (d >= startOfYesterday) return '昨天';
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}

const GROUP_LABELS: Record<string, string> = {
  today: '今天',
  yesterday: '昨天',
  thisWeek: '本周',
  earlier: '更早',
};

export function SessionsPage() {
  const { sessions, setCurrentSessionId, deleteSession, refreshSessions } = useSessions();
  const { addToast } = useToast();
  const navigate = useNavigate();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [exportingId, setExportingId] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = useCallback((val: string) => {
    setSearch(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(val), 300);
  }, []);

  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  const filtered = sessions.filter(s => {
    if (!debouncedSearch) return true;
    const q = debouncedSearch.toLowerCase();
    return (
      (s.title ?? '').toLowerCase().includes(q) ||
      (s.last_message_preview ?? '').toLowerCase().includes(q)
    );
  });

  const groups = groupByTime(filtered);
  const groupOrder = ['today', 'yesterday', 'thisWeek', 'earlier'] as const;
  const hasAny = groupOrder.some(k => groups[k].length > 0);

  function handleOpen(sessionId: string) {
    setCurrentSessionId(sessionId);
    navigate('/');
  }

  function handleDeleteClick(e: React.MouseEvent, sessionId: string) {
    e.stopPropagation();
    setDeleteTarget(sessionId);
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteSession(deleteTarget);
      addToast('会话已删除', 'success');
    } catch {
      addToast('删除失败', 'error');
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  }

  async function handleExport(e: React.MouseEvent, sessionId: string, title: string | null) {
    e.stopPropagation();
    setExportingId(sessionId);
    try {
      const res = await api.sessions.listMessages(sessionId, { per_page: 1000 });
      const messages = res.items;

      const lines: string[] = [`# ${title ?? '(未命名)'}\n`];
      for (const msg of messages) {
        const roleLabel = msg.role === 'user' ? '**用户**' : '**助手**';
        const text = msg.content
          .filter(b => b.type === 'text')
          .map(b => b.text ?? '')
          .join('\n');
        if (text) lines.push(`${roleLabel}\n\n${text}\n`);
      }

      const filename = `prism-session-${sessionId.slice(0, 8)}.md`;
      downloadMarkdown(lines.join('\n---\n\n'), filename);
      addToast('已导出 Markdown', 'success');
    } catch {
      addToast('导出失败', 'error');
    } finally {
      setExportingId(null);
    }
  }

  const deleteTargetSession = deleteTarget
    ? sessions.find(s => s.id === deleteTarget)
    : null;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>会话</h1>
          <p className={styles.subtitle}>每一次对话都是一次 Run,点击任一行可回到对话。</p>
        </div>
      </div>

      <div className={styles.searchRow}>
        <div className={styles.searchWrap}>
          <Icon name="search" size={14} className={styles.searchIcon} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="搜索会话…"
            value={search}
            onChange={e => handleSearchChange(e.target.value)}
          />
        </div>
      </div>

      {sessions.length === 0 ? (
        <div className={styles.empty}>
          <span className={styles.emptyText}>暂无会话，回到对话页新建一个。</span>
        </div>
      ) : !hasAny ? (
        <div className={styles.empty}>
          <span className={styles.emptyText}>没有匹配的会话。</span>
        </div>
      ) : (
        <div className={styles.groups}>
          {groupOrder.map(key => {
            const items = groups[key];
            if (items.length === 0) return null;
            return (
              <div key={key} className={styles.group}>
                <div className={styles.groupLabel}>{GROUP_LABELS[key]}</div>
                <div className={styles.cards}>
                  {items.map(session => (
                    <div
                      key={session.id}
                      className={styles.card}
                      onClick={() => handleOpen(session.id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={e => e.key === 'Enter' && handleOpen(session.id)}
                    >
                      <div className={styles.cardMain}>
                        <div className={styles.cardTitle}>
                          {session.is_pinned && (
                            <Icon name="pin" size={11} style={{ color: 'var(--amber)', marginRight: 6, flexShrink: 0 }} />
                          )}
                          <span>{session.title ?? '(未命名)'}</span>
                        </div>
                        {session.last_message_preview && (
                          <div className={styles.cardPreview}>{session.last_message_preview}</div>
                        )}
                      </div>
                      <div className={styles.cardMeta}>
                        <Badge variant="neutral">{session.status}</Badge>
                        <span className={styles.cardTime}>{formatTime(session.updated_at)}</span>
                        <div className={styles.cardActions}>
                          <button
                            className={styles.actionBtn}
                            title="导出 Markdown"
                            disabled={exportingId === session.id}
                            onClick={e => handleExport(e, session.id, session.title)}
                            aria-label="导出"
                          >
                            <Icon name="download" size={13} />
                          </button>
                          <button
                            className={`${styles.actionBtn} ${styles.actionBtnDanger}`}
                            title="删除会话"
                            onClick={e => handleDeleteClick(e, session.id)}
                            aria-label="删除"
                          >
                            <Icon name="close" size={13} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="删除会话"
        width={400}
      >
        <p style={{ color: 'var(--ink-2)', lineHeight: 1.6, marginBottom: 20 }}>
          确定要删除这个会话吗？
          {deleteTargetSession?.title && (
            <strong style={{ display: 'block', marginTop: 6 }}>
              "{deleteTargetSession.title}"
            </strong>
          )}
          此操作不可撤销。
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Button variant="ghost" onClick={() => setDeleteTarget(null)} disabled={deleting}>
            取消
          </Button>
          <Button variant="danger" onClick={handleDeleteConfirm} loading={deleting}>
            删除
          </Button>
        </div>
      </Modal>
    </div>
  );
}
