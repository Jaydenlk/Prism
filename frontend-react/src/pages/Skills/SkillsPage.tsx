import { useEffect, useState } from 'react';
import { Icon } from '@/components/Icon/Icon';
import { Spinner } from '@/components/Spinner/Spinner';
import { useToast } from '@/components/Toast/ToastContext';
import * as api from '@/api/client';
import type { Marketplace, SkillInstall, SkillPackage } from '@/api/types';
import { useDebounce } from '@/hooks/useDebounce';
import { SkillCard } from './SkillCard';
import { SkillDetailPanel } from './SkillDetailPanel';
import styles from './SkillsPage.module.css';

const POPULAR_SOURCES = ['superpowers', 'gstake', 'claude-skills'];

type SourceFilter = 'all' | 'local' | 'github' | 'marketplace' | 'context7';

const SOURCE_OPTIONS: { value: SourceFilter; label: string }[] = [
  { value: 'all',         label: '全部' },
  { value: 'local',       label: '本地' },
  { value: 'github',      label: 'GitHub' },
  { value: 'marketplace', label: '市场' },
  { value: 'context7',    label: 'Docs' },
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
  const [showDirectInstall, setShowDirectInstall] = useState(false);
  const [directUrl, setDirectUrl]             = useState('');
  const [directInstalling, setDirectInstalling] = useState(false);

  // Marketplace source management
  const [marketplaces, setMarketplaces]       = useState<Marketplace[]>([]);
  const [showAddSource, setShowAddSource]     = useState(false);
  const [sourceInput, setSourceInput]         = useState('');
  const [addingSource, setAddingSource]       = useState(false);

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

  async function loadMarketplaces() {
    try {
      const data = await api.marketplaces.list();
      setMarketplaces(Array.isArray(data) ? data : []);
    } catch {
      // non-fatal
    }
  }

  async function handleAddSource() {
    const raw = sourceInput.trim();
    if (!raw) return;
    // Accept owner/repo or full GitHub URL
    const ownerRepo = raw.replace(/^https?:\/\/github\.com\//, '').replace(/\/$/, '');
    const name = ownerRepo.split('/').pop() ?? ownerRepo;
    const url = ownerRepo.startsWith('http') ? ownerRepo : `https://github.com/${ownerRepo}`;
    setAddingSource(true);
    try {
      await api.marketplaces.create({ url, name });
      addToast(`已添加来源 ${name}`, 'success');
      setSourceInput('');
      setShowAddSource(false);
      await loadMarketplaces();
      await doSearch(debouncedQ, source);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '添加失败';
      addToast(msg, 'error');
    }
    setAddingSource(false);
  }

  async function handleRemoveSource(id: string, name: string) {
    try {
      await api.marketplaces.delete(id);
      addToast(`已移除来源 ${name}`, 'success');
      await loadMarketplaces();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '移除失败';
      addToast(msg, 'error');
    }
  }

  useEffect(() => {
    loadInstalled();
    loadMarketplaces();
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

  async function handleDirectInstall() {
    const url = directUrl.trim();
    if (!url) return;
    setDirectInstalling(true);
    try {
      await api.skills.installByUrl(url);
      addToast(`已安装 ${url}`, 'success');
      setDirectUrl('');
      setShowDirectInstall(false);
      await loadInstalled();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '安装失败';
      addToast(msg, 'error');
    }
    setDirectInstalling(false);
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

      {/* Marketplace source management */}
      <div className={styles.sourceBar}>
        <div className={styles.sourceBarRow}>
          <span className={styles.sourceBarLabel}>来源管理</span>
          <div className={styles.sourcePills}>
            {marketplaces.map(m => (
              <span key={m.id} className={styles.sourcePill}>
                {m.name} ✓
                <button
                  className={styles.sourcePillRemove}
                  onClick={() => handleRemoveSource(m.id, m.name)}
                  aria-label={`移除 ${m.name}`}
                >
                  ×
                </button>
              </span>
            ))}
            <button
              className={[styles.sourcePill, styles.sourcePillAdd].join(' ')}
              onClick={() => setShowAddSource(v => !v)}
            >
              + 添加来源
            </button>
          </div>
        </div>
        {showAddSource && (
          <div className={styles.sourceAddRow}>
            <input
              className={styles.sourceAddInput}
              type="text"
              placeholder="owner/repo 或 GitHub URL"
              value={sourceInput}
              onChange={e => setSourceInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !addingSource && handleAddSource()}
              autoFocus
            />
            <button
              className={styles.sourceAddBtn}
              onClick={handleAddSource}
              disabled={addingSource || !sourceInput.trim()}
            >
              {addingSource ? <Spinner size={12} /> : '添加'}
            </button>
            <div className={styles.sourceQuickLinks}>
              常用来源：
              {POPULAR_SOURCES.map(s => (
                <button
                  key={s}
                  className={styles.sourceQuickLink}
                  onClick={() => {
                    setSourceInput(s);
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
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

      {/* Direct install */}
      <div className={styles.directInstall}>
        <button
          className={styles.directInstallToggle}
          onClick={() => setShowDirectInstall(v => !v)}
        >
          <Icon
            name="chevron"
            size={12}
            style={{
              color: 'var(--ink-4)',
              transform: showDirectInstall ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s ease',
            }}
          />
          知道地址？直接安装
        </button>
        {showDirectInstall && (
          <div className={styles.directInstallBody}>
            <div className={styles.directInstallRow}>
              <input
                className={styles.directInstallInput}
                type="text"
                placeholder="GitHub URL 或 owner/repo"
                value={directUrl}
                onChange={e => setDirectUrl(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !directInstalling && handleDirectInstall()}
              />
              <button
                className={styles.directInstallBtn}
                onClick={handleDirectInstall}
                disabled={directInstalling || !directUrl.trim()}
              >
                {directInstalling ? <Spinner size={12} /> : '安装'}
              </button>
            </div>
            <p className={styles.directInstallHint}>
              示例: anthropics/superpowers 或 https://github.com/user/skill
            </p>
          </div>
        )}
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
                {q ? `没有找到 "${q}"` : '暂无可搜索内容'}
              </p>
              {q ? (
                <>
                  <ul className={styles.emptyReasons}>
                    <li>该技能可能在未注册的来源中 — 试试添加来源</li>
                    <li>拼写不完整 — 试试更短的关键词</li>
                  </ul>
                  <div className={styles.emptyActions}>
                    <button
                      className={styles.emptyActionBtn}
                      onClick={() => setShowAddSource(true)}
                    >
                      添加来源
                    </button>
                    <button
                      className={styles.emptyActionBtnGhost}
                      onClick={() => setShowDirectInstall(true)}
                    >
                      直接安装
                    </button>
                  </div>
                </>
              ) : (
                <p className={styles.emptySub}>
                  添加来源后即可浏览和搜索，或直接输入 GitHub URL 安装
                </p>
              )}
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
                  stars={sk.stars}
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
