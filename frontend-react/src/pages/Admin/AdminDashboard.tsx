import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import type { SystemStats } from '@/api/types';
import { StatCard } from '@/components/StatCard/StatCard';
import styles from './AdminDashboard.module.css';

export function AdminDashboard() {
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');

    api.admin.getDashboard()
      .then(data => {
        if (!cancelled) setStats(data);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return <div className={styles.loadingState}>正在加载…</div>;
  }

  if (err) {
    return <div className={styles.errorState}>加载失败: {err}</div>;
  }

  const totalUsers = stats?.active_users_24h ?? 0;
  const runs24h = stats?.runs_24h ?? 0;
  const cost7d = stats?.cost_usd_7d ?? 0;
  const cacheSavings = stats?.cache_savings_usd_7d ?? 0;
  const activeSessions = stats?.active_sessions ?? 0;
  const runs7d = stats?.runs_7d ?? 0;
  const avgTurns = runs7d > 0 ? (runs7d / Math.max(1, activeSessions)).toFixed(1) : '—';

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>系统概览</h1>
        <p className={styles.subtitle}>实时系统指标一览</p>
      </div>

      <div className={styles.grid}>
        <StatCard label="活跃用户 (24h)" value={String(totalUsers)} />
        <StatCard label="24h Runs" value={String(runs24h)} />
        <StatCard label="7d 成本" value={`$${cost7d.toFixed(2)}`} />
        <StatCard label="Cache 节省" value={`$${cacheSavings.toFixed(2)}`} />
        <StatCard label="活跃会话" value={String(activeSessions)} />
        <StatCard label="平均 turns/run" value={avgTurns} />
      </div>
    </div>
  );
}
