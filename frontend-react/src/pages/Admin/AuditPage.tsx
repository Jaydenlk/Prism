import { useState, useEffect, useCallback } from 'react';
import * as api from '@/api/client';
import type { AuditLog } from '@/api/types';
import { Button } from '@/components/Button/Button';
import styles from './AuditPage.module.css';

function severityColor(severity: string): string {
  if (severity === 'critical') return 'var(--rust)';
  if (severity === 'warning') return 'var(--amber)';
  return 'var(--ink-3)';
}

export function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    action: '',
    user_id: '',
    start_date: '',
    end_date: '',
  });
  const [pendingFilters, setPendingFilters] = useState(filters);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [exporting, setExporting] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');

    api.admin.listAuditLogs({
      action: filters.action || undefined,
      user_id: filters.user_id || undefined,
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      page,
      limit: 50,
    })
      .then(data => {
        if (cancelled) return;
        setLogs(data.items);
        setTotal(data.total);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [filters, page]);

  useEffect(() => {
    return load();
  }, [load]);

  function applyFilters() {
    setFilters(pendingFilters);
    setPage(1);
  }

  async function handleExport() {
    setExporting(true);
    try {
      await api.admin.exportAuditLogsCSV({
        action: filters.action || undefined,
        user_id: filters.user_id || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
      });
    } catch (e) {
      setErr((e as Error).message ?? '导出失败');
    } finally {
      setExporting(false);
    }
  }

  const perPage = 50;
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>审计日志</h1>
        <Button
          size="sm"
          variant="ghost"
          icon="download"
          loading={exporting}
          onClick={handleExport}
        >
          导出 CSV
        </Button>
      </div>

      <div className={styles.filters}>
        <input
          className={styles.filterInput}
          placeholder="操作类型…"
          value={pendingFilters.action}
          onChange={e => setPendingFilters(f => ({ ...f, action: e.target.value }))}
        />
        <input
          className={styles.filterInput}
          placeholder="用户 ID…"
          value={pendingFilters.user_id}
          onChange={e => setPendingFilters(f => ({ ...f, user_id: e.target.value }))}
        />
        <input
          className={styles.filterInput}
          type="date"
          value={pendingFilters.start_date}
          onChange={e => setPendingFilters(f => ({ ...f, start_date: e.target.value }))}
        />
        <input
          className={styles.filterInput}
          type="date"
          value={pendingFilters.end_date}
          onChange={e => setPendingFilters(f => ({ ...f, end_date: e.target.value }))}
        />
        <Button size="sm" onClick={applyFilters}>筛选</Button>
      </div>

      {err && <div className={styles.errorState}>加载失败: {err}</div>}

      {loading ? (
        <div className={styles.loadingState}>正在加载…</div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>时间</th>
                <th>用户</th>
                <th>操作</th>
                <th>资源</th>
                <th>级别</th>
                <th>详情</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={6} className={styles.emptyCell}>暂无日志</td>
                </tr>
              ) : (
                logs.map(log => {
                  const isExpanded = expandedId === log.id;
                  const detailStr = JSON.stringify(log.details);
                  const truncated = detailStr.length > 60 ? detailStr.slice(0, 60) + '…' : detailStr;

                  return (
                    <tr key={log.id} className={styles.logRow}>
                      <td className={styles.timestamp}>
                        {new Date(log.created_at).toLocaleString('zh-CN', {
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </td>
                      <td className={styles.userId}>{log.user_id ?? '—'}</td>
                      <td className={styles.action}>{log.action}</td>
                      <td className={styles.resource}>
                        {log.resource_type ? `${log.resource_type}${log.resource_id ? ':' + log.resource_id : ''}` : '—'}
                      </td>
                      <td>
                        <span style={{ color: severityColor(log.severity), fontSize: 12, fontWeight: 500 }}>
                          {log.severity}
                        </span>
                      </td>
                      <td
                        className={`${styles.details} ${isExpanded ? styles.detailsExpanded : ''}`}
                        onClick={() => setExpandedId(isExpanded ? null : log.id)}
                        title="点击展开"
                      >
                        <code className={styles.detailCode}>
                          {isExpanded ? detailStr : truncated}
                        </code>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {!loading && totalPages > 1 && (
        <div className={styles.pagination}>
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
          >
            上一页
          </Button>
          <span className={styles.pageInfo}>{page} / {totalPages}</span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  );
}
