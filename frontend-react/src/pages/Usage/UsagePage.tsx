import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import styles from './UsagePage.module.css';

// Typed shape of providers.usage() response (matches backend schema)
interface ProviderUsageRow {
  provider_id?: string;
  provider_name?: string;
  input_tokens?: number;
  output_tokens?: number;
  cache_hit_tokens?: number;
  cache_creation_tokens?: number;
  cost_usd?: number;
  runs?: number;
}

interface UsageSummary {
  total_input_tokens?: number;
  total_output_tokens?: number;
  cache_hit_ratio?: number;
  estimated_cache_savings_usd?: number;
  total_runs?: number;
}

interface UsageResponse {
  summary?: UsageSummary;
  by_provider?: ProviderUsageRow[];
}

type DayRange = 7 | 30;

function fmtTok(n: number | undefined): string {
  const v = n ?? 0;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
  return String(v);
}

function getDateRange(days: DayRange): { start_date: string; end_date: string } {
  const end = new Date();
  const start = new Date(Date.now() - days * 24 * 3600 * 1000);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { start_date: fmt(start), end_date: fmt(end) };
}

export function UsagePage() {
  const [days, setDays] = useState<DayRange>(7);
  const [data, setData] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');
    setData(null);

    const { start_date, end_date } = getDateRange(days);

    api.providers
      .usage({ group_by: 'day', start_date, end_date })
      .then(resp => {
        if (cancelled) return;
        setData((resp as UsageResponse) ?? {});
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [days]);

  const summary = data?.summary ?? {};
  const byProvider = data?.by_provider ?? [];
  const totalIn = summary.total_input_tokens ?? 0;
  const totalOut = summary.total_output_tokens ?? 0;
  const cacheHit = summary.cache_hit_ratio ?? 0;
  const savings = summary.estimated_cache_savings_usd ?? 0;
  const runs = summary.total_runs ?? 0;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>用量统计</h1>
          <p className={styles.subtitle}>
            Prompt cache 命中率越高，省越多。
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
      ) : (
        <>
          <div className={styles.statsGrid}>
            <StatCard label="缓存命中率" featured>
              <span className={styles.statValue}>{(cacheHit * 100).toFixed(1)}</span>
              <span className={styles.statUnit}>%</span>
              <div className={styles.statSub}>cache_hit_tokens / input</div>
            </StatCard>

            <StatCard label={`${days} 天 input tokens`}>
              <span className={styles.statValue}>{fmtTok(totalIn)}</span>
            </StatCard>

            <StatCard label={`${days} 天 output tokens`}>
              <span className={styles.statValue}>{fmtTok(totalOut)}</span>
            </StatCard>

            <StatCard label="省下估算 (USD)">
              <span className={styles.statValue}>${savings.toFixed(2)}</span>
              <div className={styles.statSub}>共 {runs} 次运行</div>
            </StatCard>
          </div>

          <div className={styles.sectionTitle}>分 Provider</div>

          {byProvider.length === 0 ? (
            <div className={styles.emptyProviders}>
              这 {days} 天还没有任何 run 消耗 tokens。
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>输入</th>
                    <th>输出</th>
                    <th>缓存命中</th>
                    <th>缓存创建</th>
                    <th>花费 (USD)</th>
                    <th>Runs</th>
                  </tr>
                </thead>
                <tbody>
                  {byProvider.map((p, i) => (
                    <tr key={p.provider_id ?? p.provider_name ?? i}>
                      <td className={styles.providerName}>{p.provider_name ?? '(unknown)'}</td>
                      <td className={styles.mono}>{fmtTok(p.input_tokens)}</td>
                      <td className={styles.mono}>{fmtTok(p.output_tokens)}</td>
                      <td className={`${styles.mono} ${styles.teal}`}>{fmtTok(p.cache_hit_tokens)}</td>
                      <td className={styles.mono}>{fmtTok(p.cache_creation_tokens)}</td>
                      <td className={styles.mono}>${(p.cost_usd ?? 0).toFixed(4)}</td>
                      <td className={`${styles.mono} ${styles.muted}`}>{p.runs ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface StatCardProps {
  label: string;
  featured?: boolean;
  children: React.ReactNode;
}

function StatCard({ label, featured, children }: StatCardProps) {
  return (
    <div className={`${styles.statCard} ${featured ? styles.statCardFeatured : ''}`}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statBody}>{children}</div>
    </div>
  );
}
