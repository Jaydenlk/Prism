import { useEffect, useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import { Spinner } from '@/components/Spinner/Spinner';
import { useToast } from '@/components/Toast/ToastContext';
import * as api from '@/api/client';
import type { SkillInstall, SkillPackage } from '@/api/types';
import { useDebounce } from '@/hooks/useDebounce';
import { SkillCard } from './SkillCard';
import { SkillDetailPanel } from './SkillDetailPanel';
import styles from './SkillsPage.module.css';

type SourceFilter = 'all' | 'local' | 'github' | 'marketplace';

const SOURCE_OPTIONS: { value: SourceFilter; label: string }[] = [
  { value: 'all',         label: '全部' },
  { value: 'local',       label: '本地' },
  { value: 'github',      label: 'GitHub' },
  { value: 'marketplace', label: '市场' },
];

export function SkillsPage() {
  const { addToast } = useToast();

  const [q, setQ]                             = useState('');
  const [source, setSource]                   = useState<SourceFilter>('all');
  const [searchResults, setSearchResults]     = useState<SkillPackage[]>([]);
  const [searching, setSearching]             = useState(false);
  const [searchErr, setSearchErr]             = useState('');
  const [installed, setInstalled]             = useState<SkillInstall[]>([]);
  const [actionLoading, setActionLoading]     = useState<string | null>(null);
  const [detailSkill, setDetailSkill]         = useState<SkillPackage | null>(null);

  const debouncedQ = useDebounce(q, 300);

  // ── Loaders ──────────────────────────────────────────────────────────────
  async function loadInstalled() {
    try {
      const data = await api.skills.listInstalled();
      setInstalled(Array.isArray(data) ? data : []);
    } catch {
      // non-fatal
    }
  }

  async function doSearch(searchQ: string, searchSource: SourceFilter) {
    setSearching(true);
    setSearchErr('');
    try {
      const data = await api.skills.search({
        q: searchQ || undefined,
        source: searchSource !== 'all' ? searchSource : undefined,
        limit: 20,
      });
      setSearchResults(Array.isArray(data) ? data : []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '搜索失败';
      setSearchErr(msg);
      setSearchResults([]);
    }
    setSearching(false);
  }

  useEffect(() => {
    loadInstalled();
  }, []);

  useEffect(() => {
    doSearch(debouncedQ, source);
  }, [debouncedQ, source]);

  // ── Helpers ───────────────────────────────────────────────────────────────
  function isInstalled(name: string) {
    return installed.some(s => s.skill_name === name);
  }

  // ── Actions ───────────────────────────────────────────────────────────────
  async function handleInstall(sk: SkillPackage) {
    setActionLoading(sk.name);
    try {
      await api.skills.install({
        skill_name: sk.name,
        source: sk.source,
        source_url: sk.source_url ?? undefined,
        version: sk.version ?? undefined,
        marketplace_id: sk.marketplace_id ?? undefined,
      });
      addToast(`已安装 ${sk.name}`, 'success');
      await loadInstalled();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '安装失败';
      addToast(msg, 'error');
    }
    setActionLoading(null);
  }

  async function handleUninstall(name: string) {
    setActionLoading(name);
    try {
      await api.skills.uninstall(name);
      addToast(`已卸载 ${name}`, 'success');
      await loadInstalled();
      if (detailSkill?.name === name) setDetailSkill(null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '卸载失败';
      addToast(msg, 'error');
    }
    setActionLoading(null);
  }

  async function handleToggleEnabled(sk: SkillInstall) {
    const name = sk.skill_name;
    const meta = sk.metadata as { enabled?: boolean } | undefined;
    const newEnabled = !(meta?.enabled ?? true);
    setActionLoading(name);
    try {
      await api.skills.patch(name, { enabled: newEnabled });
      addToast(newEnabled ? `已启用 ${name}` : `已禁用 ${name}`, 'success');
      await loadInstalled();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '操作失败';
      addToast(msg, 'error');
    }
    setActionLoading(null);
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.pageHead}>
        <h1 className={styles.pageTitle}>技能市场</h1>
        <p className={styles.pageSub}>
          Skill 是一份 Markdown 加可选钩子。浏览、搜索并安装到你的 Prism。
        </p>
      </div>

      {/* Search + filter row */}
      <div className={styles.searchRow}>
        <div className={styles.searchWrap}>
          <Icon name="search" size={15} style={{ color: 'var(--ink-4)', flexShrink: 0 }} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="搜索技能名称…（300ms 防抖）"
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </div>
        <div className={styles.filterPills}>
          {SOURCE_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={[styles.pill, source === opt.value ? styles.pillActive : ''].filter(Boolean).join(' ')}
              onClick={() => setSource(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Search error */}
      {searchErr && (
        <div className={styles.searchErr}>{searchErr}</div>
      )}

      {/* Results grid */}
      <div className={styles.content}>
        <section>
          {searching ? (
            <div className={styles.loadingState}>
              <Spinner size={16} />
              <span>搜索中…</span>
            </div>
          ) : searchResults.length === 0 ? (
            <div className={styles.emptyState}>
              <p className={styles.emptyTitle}>
                {q ? `未找到 "${q}" 相关的技能` : '暂无可搜索内容'}
              </p>
              <p className={styles.emptySub}>
                {q
                  ? '试试更短的关键词，或清除筛选'
                  : '可在 Marketplace tab 注册目录，或从本地上传 SKILL.md'}
              </p>
            </div>
          ) : (
            <div className={styles.grid}>
              {searchResults.map(sk => (
                <SkillCard
                  key={sk.name}
                  name={sk.name}
                  description={sk.description}
                  source={sk.source}
                  sourceUrl={sk.source_url}
                  installed={isInstalled(sk.name)}
                  onInstall={() => handleInstall(sk)}
                  onUninstall={() => handleUninstall(sk.name)}
                  onClick={() => setDetailSkill(sk)}
                />
              ))}
            </div>
          )}
        </section>

        {/* Installed section */}
        {installed.length > 0 && (
          <section className={styles.installedSection}>
            <h2 className={styles.sectionTitle}>已安装 ({installed.length})</h2>
            <div className={styles.installedList}>
              {installed.map(sk => {
                const meta = sk.metadata as { enabled?: boolean } | undefined;
                const enabled = meta?.enabled ?? true;
                const acting = actionLoading === sk.skill_name;
                return (
                  <div key={sk.id} className={styles.installedItem}>
                    <div className={styles.installedInfo}>
                      <span className={styles.installedName}>{sk.skill_name}</span>
                      <span className={styles.installedSource}>{sk.source}</span>
                    </div>
                    <div className={styles.installedActions}>
                      <button
                        className={[styles.toggleBtn, enabled ? styles.toggleOn : styles.toggleOff].join(' ')}
                        onClick={() => handleToggleEnabled(sk)}
                        disabled={acting}
                        aria-label={enabled ? '禁用' : '启用'}
                      >
                        {acting ? <Spinner size={12} /> : (enabled ? '已启用' : '已禁用')}
                      </button>
                      <button
                        className={styles.uninstallBtn}
                        onClick={() => handleUninstall(sk.skill_name)}
                        disabled={acting}
                      >
                        卸载
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {/* Detail panel */}
      {detailSkill && (
        <SkillDetailPanel
          skill={detailSkill}
          installed={isInstalled(detailSkill.name)}
          onInstall={() => handleInstall(detailSkill)}
          onUninstall={() => handleUninstall(detailSkill.name)}
          onClose={() => setDetailSkill(null)}
        />
      )}
    </div>
  );
}
