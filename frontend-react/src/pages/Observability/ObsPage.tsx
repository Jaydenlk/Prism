import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import { StatCard } from '@/components/StatCard/StatCard';
import styles from './ObsPage.module.css';

// Typed shape of harness.analytics() response (matches backend schema)
interface HarnessTotals {
  tool_calls?: number;
  tool_errors?: number;
  compaction_events?: number;
  guardrail_triggers?: number;
  permission_denials?: number;
  hook_fires?: number;
  loop_detections?: number;
  fork_count?: number;
}

interface HarnessAverages {
  turns_per_run?: number;
}

interface HarnessCacheStats {
  hit_ratio?: number;
}

interface PeakContextUsage {
  avg?: number;
}

interface AnalyticsResponse {
  runs_analyzed?: number;
  totals?: HarnessTotals;
  averages?: HarnessAverages;
  cache_stats?: HarnessCacheStats;
  peak_context_usage?: PeakContextUsage;
}

type DayRange = 7 | 30;

// Signal indicators: derived from analytics data
interface Signal {
  label: string;
  status: 'healthy' | 'warning' | 'critical';
  value: string;
}

function deriveSignals(data: AnalyticsResponse): Signal[] {
  const totals = data.totals ?? {};
  const averages = data.averages ?? {};
  const cache = data.cache_stats ?? {};
  const peak = data.peak_context_usage ?? {};
  const runs = data.runs_analyzed ?? 0;

  const toolErrRate = (totals.tool_calls ?? 0) > 0
    ? (totals.tool_errors ?? 0) / totals.tool_calls!
    : 0;

  const cacheHit = cache.hit_ratio ?? 0;
  const avgPeak = peak.avg ?? 0;
  const compRate = runs > 0 ? (totals.compaction_events ?? 0) / runs : 0;
  const loopDet = totals.loop_detections ?? 0;
  const guardrail = totals.guardrail_triggers ?? 0;
  const permDenials = totals.permission_denials ?? 0;
  const turnsPerRun = averages.turns_per_run ?? 0;

  return [
    {
      label: '工具错误率',
      status: toolErrRate > 0.1 ? 'critical' : toolErrRate > 0.03 ? 'warning' : 'healthy',
      value: `${(toolErrRate * 100).toFixed(1)}%`,
    },
    {
      label: 'Cache 命中率',
      status: cacheHit < 0.2 ? 'warning' : 'healthy',
      value: `${(cacheHit * 100).toFixed(1)}%`,
    },
    {
      label: '峰值上下文',
      status: avgPeak > 0.9 ? 'critical' : avgPeak > 0.7 ? 'warning' : 'healthy',
      value: `${(avgPeak * 100).toFixed(0)}%`,
    },
    {
      label: 'Compaction 率',
      status: compRate > 0.5 ? 'warning' : 'healthy',
      value: `${(compRate * 100).toFixed(1)}%`,
    },
    {
      label: '循环检测',
      status: loopDet > 0 ? 'warning' : 'healthy',
      value: String(loopDet),
    },
    {
      label: '护栏触发',
      status: guardrail > 5 ? 'warning' : 'healthy',
      value: String(guardrail),
    },
    {
      label: '权限拒绝',
      status: permDenials > 0 ? 'warning' : 'healthy',
      value: String(permDenials),
    },
    {
      label: '平均轮次',
      status: turnsPerRun > 20 ? 'warning' : 'healthy',
      value: turnsPerRun.toFixed(1),
    },
  ];
}

export function ObsPage() {
  const [days, setDays] = useState<DayRange>(7);
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');
    setData(null);

    api.harness
      .analytics({ days })
      .then(resp => {
        if (cancelled) return;
        setData((resp as AnalyticsResponse) ?? {});
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [days]);

  const runsAnalyzed = data?.runs_analyzed ?? 0;
  const totals = data?.totals ?? {};
  const averages = data?.averages ?? {};
  const cacheStats = data?.cache_stats ?? {};
  const peak = data?.peak_context_usage ?? {};

  const toolErrRate = (totals.tool_calls ?? 0) > 0
    ? ((totals.tool_errors ?? 0) / totals.tool_calls! * 100).toFixed(1)
    : '0.0';
  const compactionRate = ((totals.compaction_events ?? 0) / (runsAnalyzed || 1) * 100).toFixed(1);
  const cacheHitPct = ((cacheStats.hit_ratio ?? 0) * 100).toFixed(1);
  const signals = data ? deriveSignals(data) : [];

  const governanceItems = [
    { label: '护栏触发', val: totals.guardrail_triggers ?? 0, warn: (totals.guardrail_triggers ?? 0) > 0 },
    { label: '权限拒绝', val: totals.permission_denials ?? 0, warn: (totals.permission_denials ?? 0) > 0 },
    { label: 'Hook 触发', val: totals.hook_fires ?? 0, warn: false },
    { label: '循环检测', val: totals.loop_detections ?? 0, warn: (totals.loop_detections ?? 0) > 0 },
    { label: 'Fork 数', val: totals.fork_count ?? 0, warn: false },
    { label: '峰值上下文', val: `${((peak.avg ?? 0) * 100).toFixed(0)}%`, warn: (peak.avg ?? 0) > 0.9 },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>可观测性</h1>
          <p className={styles.subtitle}>
            {loading ? '正在加载…' : `${days} 天窗口 · ${runsAnalyzed} 次运行分析。`}
          </p>
        </div>
        <div className={styles.rangeSelector}>
          {([7, 30] as DayRange[]).map(d => (
            <button
              key={d}
              className={`${styles.rangeBtn} ${days === d ? styles.rangeBtnActive : ''}`}
              onClick={() => setDays(d)}
            >
              {d}天
            </button>
          ))}
        </div>
      </div>

      {err && (
        <div className={styles.errorNotice}>加载失败: {err}</div>
      )}

      {loading ? (
        <div className={styles.loadingState}>
          <span style={{ fontFamily: 'var(--serif)', fontStyle: 'italic', color: 'var(--ink-4)' }}>
            正在加载…
          </span>
        </div>
      ) : runsAnalyzed === 0 ? (
        <div className={styles.emptyState}>
          暂无运行数据 — 发起一次对话后回来看。
        </div>
      ) : (
        <>
          {/* Signal indicators row */}
          <div className={styles.signals}>
            {signals.map(sig => (
              <div key={sig.label} className={`${styles.signal} ${styles[sig.status]}`}>
                <span className={styles.signalDot} />
                <span className={styles.signalLabel}>{sig.label}</span>
                <span className={styles.signalValue}>{sig.value}</span>
              </div>
            ))}
          </div>

          {/* Main stat cards */}
          <div className={styles.statsGrid}>
            <StatCard label="平均轮次" featured>
              <span className={styles.statValue}>{(averages.turns_per_run ?? 0).toFixed(1)}</span>
              <div className={styles.statSub}>turns / run</div>
            </StatCard>

            <StatCard label="工具错误率">
              <span className={styles.statValue}>{toolErrRate}</span>
              <span className={styles.statUnit}>%</span>
              <div className={`${styles.statSub} ${(totals.tool_errors ?? 0) > 0 ? styles.statSubWarn : ''}`}>
                {totals.tool_errors ?? 0} / {totals.tool_calls ?? 0}
              </div>
            </StatCard>

            <StatCard label="Compaction 率">
              <span className={styles.statValue}>{compactionRate}</span>
              <span className={styles.statUnit}>%</span>
              <div className={styles.statSub}>{totals.compaction_events ?? 0} 次</div>
            </StatCard>

            <StatCard label="Cache 命中率">
              <span className={styles.statValue}>{cacheHitPct}</span>
              <span className={styles.statUnit}>%</span>
              <div className={`${styles.statSub} ${styles.statSubTeal}`}>
                峰值上下文 {((peak.avg ?? 0) * 100).toFixed(0)}%
              </div>
            </StatCard>
          </div>

          {/* Governance section */}
          <div className={styles.sectionTitle}>Harness 治理概览</div>
          <div className={styles.governanceCard}>
            <div className={styles.governanceGrid}>
              {governanceItems.map(item => (
                <div key={item.label} className={styles.govItem}>
                  <div className={styles.govLabel}>{item.label}</div>
                  <div className={`${styles.govValue} ${item.warn ? styles.govValueWarn : ''}`}>
                    {item.val}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

