import { useState, useEffect, useMemo } from 'react';
import type { IconName } from '@/components/Icon/Icon';
import { Icon, PrismMark } from '@/components/Icon/Icon';
import { Button } from '@/components/Button/Button';
import { useAuth } from '@/hooks/useAuth';
import { useSessions } from '@/hooks/useSessions';
import { groupByTime, formatTime } from '@/utils/time';
import styles from './Sidebar.module.css';

interface NavItem {
  path: string;
  icon: IconName;
  label: string;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/', icon: 'chat', label: '对话' },
  { path: '/sessions', icon: 'sessions', label: '会话' },
  { path: '/usage', icon: 'usage', label: '用量' },
  { path: '/skills', icon: 'skills', label: '技能市场' },
  { path: '/plugins', icon: 'plugin', label: '插件构建' },
  { path: '/settings', icon: 'settings', label: '设置' },
  { path: '/observability', icon: 'layers', label: '可观测性' },
  { path: '/admin', icon: 'admin', label: '管理', adminOnly: true },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  currentPage: string;
  onNavigate: (page: string) => void;
}

export function Sidebar({ open, onClose, currentPage, onNavigate }: SidebarProps) {
  const { user } = useAuth();
  const { sessions, currentSessionId, createSession, setCurrentSessionId } = useSessions();
  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const groups = useMemo(() => {
    const filtered = debouncedQ
      ? sessions.filter(s =>
          (s.title ?? '').toLowerCase().includes(debouncedQ.toLowerCase()) ||
          (s.last_message_preview ?? '').toLowerCase().includes(debouncedQ.toLowerCase())
        )
      : sessions;
    return groupByTime(filtered);
  }, [sessions, debouncedQ]);

  async function handleNewChat() {
    const session = await createSession();
    setCurrentSessionId(session.id);
    onNavigate('/');
  }

  function handleSessionClick(id: string) {
    setCurrentSessionId(id);
    onNavigate('/');
  }

  const visibleNavItems = NAV_ITEMS.filter(
    item => !item.adminOnly || user?.role === 'admin'
  );

  const GROUP_LABELS: Record<string, string> = {
    today: '今天',
    yesterday: '昨天',
    thisWeek: '本周',
    earlier: '更早',
  };

  return (
    <>
      {open && <div className={styles.backdrop} onClick={onClose} />}
      <aside className={`${styles.sidebar}${open ? ` ${styles.open}` : ''}`}>
        <div className={styles.header}>
          <PrismMark size={22} />
          <span className={styles.brand}>Prism 棱镜</span>
        </div>

        <div className={styles.newChatWrap}>
          <Button variant="ghost" icon="plus" style={{ width: '100%', justifyContent: 'center' }} onClick={handleNewChat}>
            新对话
          </Button>
        </div>

        <div className={styles.searchWrap}>
          <span className={styles.searchIcon}>
            <Icon name="search" size={13} />
          </span>
          <input
            className={styles.searchInput}
            placeholder="搜索会话…"
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </div>

        <div className={styles.sessionList}>
          {sessions.length === 0 && (
            <div className={styles.emptyMsg}>暂无会话</div>
          )}
          {(['today', 'yesterday', 'thisWeek', 'earlier'] as const).map(groupKey => {
            const group = groups[groupKey];
            if (!group.length) return null;
            return (
              <div key={groupKey}>
                <div className={styles.groupLabel}>{GROUP_LABELS[groupKey]}</div>
                {group.map(session => (
                  <div
                    key={session.id}
                    className={`${styles.sessionItem}${session.id === currentSessionId ? ` ${styles.active}` : ''}`}
                    onClick={() => handleSessionClick(session.id)}
                  >
                    <div className={styles.sessionTitle}>
                      {session.is_pinned && <Icon name="pin" size={10} style={{ color: 'var(--amber)', flexShrink: 0 }} />}
                      {session.title ?? '新对话'}
                    </div>
                    <div className={styles.sessionTime}>{formatTime(session.updated_at)}</div>
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        <nav className={styles.nav} aria-label="主导航">
          {visibleNavItems.map(item => (
            <button
              key={item.path}
              className={`${styles.navItem}${currentPage === item.path ? ` ${styles.activeNav}` : ''}`}
              onClick={() => onNavigate(item.path)}
            >
              <Icon name={item.icon} size={14} />
              {item.label}
            </button>
          ))}
        </nav>
      </aside>
    </>
  );
}
