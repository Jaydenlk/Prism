import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import type { AdminUser } from '@/api/types';
import { Badge } from '@/components/Badge/Badge';
import { Button } from '@/components/Button/Button';
import { Pagination } from '@/components/Pagination/Pagination';
import { useToast } from '@/components/Toast/ToastContext';
import styles from './UsersPage.module.css';

function roleBadge(role: string) {
  return role === 'admin' ? (
    <Badge variant="amber">admin</Badge>
  ) : (
    <Badge variant="neutral">user</Badge>
  );
}

export function UsersPage() {
  const { addToast } = useToast();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');

    api.admin.listUsers({ page, search: search || undefined })
      .then(data => {
        if (cancelled) return;
        setUsers(data.items);
        setTotal(data.total);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [page, search, refreshKey]);

  function handleSearch() {
    setSearch(searchInput);
    setPage(1);
  }

  async function handleChangeRole(user: AdminUser, newRole: 'admin' | 'user') {
    const adminCount = users.filter(u => u.role === 'admin').length;
    if (user.role === 'admin' && newRole === 'user' && adminCount <= 1) {
      addToast('无法降级唯一的管理员', 'error');
      return;
    }

    setActionLoading(user.id + '-role');
    try {
      const updated = await api.admin.changeUserRole(user.id, newRole);
      setUsers(prev => prev.map(u => u.id === updated.id ? updated : u));
      addToast(`${user.username} 已更新为 ${newRole}`, 'success');
    } catch (e) {
      addToast((e as Error).message ?? '操作失败', 'error');
    } finally {
      setActionLoading(null);
    }
  }

  async function handleDisable(user: AdminUser) {
    const adminCount = users.filter(u => u.role === 'admin').length;
    if (user.role === 'admin' && adminCount <= 1) {
      addToast('无法禁用唯一的管理员', 'error');
      return;
    }

    setActionLoading(user.id + '-disable');
    try {
      await api.admin.disableUser(user.id);
      addToast(`${user.username} 已禁用`, 'success');
      setRefreshKey(k => k + 1);
    } catch (e) {
      addToast((e as Error).message ?? '操作失败', 'error');
    } finally {
      setActionLoading(null);
    }
  }

  const perPage = 20;
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>用户管理</h1>
        <div className={styles.searchRow}>
          <input
            className={styles.searchInput}
            placeholder="搜索邮箱 / 用户名…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
          />
          <Button size="sm" onClick={handleSearch}>搜索</Button>
        </div>
      </div>

      {err && <div className={styles.errorState}>加载失败: {err}</div>}

      {loading ? (
        <div className={styles.loadingState}>正在加载…</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>用户名</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>注册时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} className={styles.emptyCell}>暂无用户</td>
                </tr>
              ) : (
                users.map(user => (
                  <tr key={user.id}>
                    <td className={styles.username}>{user.username}</td>
                    <td className={styles.email}>{user.email}</td>
                    <td>{roleBadge(user.role)}</td>
                    <td className={styles.date}>{new Date(user.created_at).toLocaleDateString('zh-CN')}</td>
                    <td>
                      <div className={styles.actions}>
                        <select
                          className={styles.roleSelect}
                          value={user.role}
                          disabled={actionLoading === user.id + '-role'}
                          onChange={e => handleChangeRole(user, e.target.value as 'admin' | 'user')}
                        >
                          <option value="user">user</option>
                          <option value="admin">admin</option>
                        </select>
                        <Button
                          variant="danger"
                          size="sm"
                          loading={actionLoading === user.id + '-disable'}
                          onClick={() => handleDisable(user)}
                        >
                          禁用
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && (
        <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
      )}
    </div>
  );
}
