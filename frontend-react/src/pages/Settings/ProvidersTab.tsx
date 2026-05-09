import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import type { Provider, ProviderPreset } from '@/api/types';
import { useToast } from '@/components/Toast/ToastContext';
import { Button } from '@/components/Button/Button';
import { Badge } from '@/components/Badge/Badge';
import { Modal } from '@/components/Modal/Modal';
import { ConfirmModal } from '@/components/ConfirmModal/ConfirmModal';
import { Spinner } from '@/components/Spinner/Spinner';
import styles from './SettingsPage.module.css';

interface ProviderFormState {
  name: string;
  protocol: 'anthropic' | 'openai';
  api_key: string;
  base_url: string;
  model_id: string;
}

const EMPTY_FORM: ProviderFormState = {
  name: '',
  protocol: 'anthropic',
  api_key: '',
  base_url: '',
  model_id: '',
};

export function ProvidersTab() {
  const { addToast } = useToast();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [presets, setPresets] = useState<ProviderPreset[]>([]);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [form, setForm] = useState<ProviderFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [ps, prs] = await Promise.all([api.providers.list(), api.providers.presets()]);
        if (!cancelled) {
          setProviders(ps);
          setPresets(prs);
        }
      } catch (err) {
        if (!cancelled) addToast(err instanceof Error ? err.message : '加载失败', 'error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [addToast]);

  async function handleTest(id: string) {
    setTestingId(id);
    try {
      const result = await api.providers.test(id);
      if (result.success) {
        addToast(`连接成功 (${result.latency_ms ?? '?'}ms)`, 'success');
      } else {
        addToast(result.error ?? '连接失败', 'error');
      }
    } catch (err) {
      addToast(err instanceof Error ? err.message : '测试失败', 'error');
    } finally {
      setTestingId(null);
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await api.providers.delete(id);
      setProviders((prev) => prev.filter((p) => p.id !== id));
      addToast('已删除', 'success');
    } catch (err) {
      addToast(err instanceof Error ? err.message : '删除失败', 'error');
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  }

  async function handleAdd() {
    if (!form.name || !form.api_key || !form.model_id) {
      addToast('请填写必填字段', 'error');
      return;
    }
    setSaving(true);
    try {
      const created = await api.providers.create({
        name: form.name,
        protocol: form.protocol,
        api_key: form.api_key,
        base_url: form.base_url,
        model_id: form.model_id,
      });
      setProviders((prev) => [...prev, created]);
      addToast('供应商已添加', 'success');
      setAddOpen(false);
      setForm(EMPTY_FORM);
    } catch (err) {
      addToast(err instanceof Error ? err.message : '添加失败', 'error');
    } finally {
      setSaving(false);
    }
  }

  function applyPreset(preset: ProviderPreset) {
    setForm((prev) => ({
      ...prev,
      name: preset.name,
      protocol: preset.protocol,
      base_url: preset.base_url,
      model_id: preset.model_id,
    }));
  }

  function protocolBadgeVariant(protocol: string): 'amber' | 'teal' {
    return protocol === 'anthropic' ? 'amber' : 'teal';
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spinner size={20} />
      </div>
    );
  }

  return (
    <>
      <div className={styles.section}>
        <div className={styles.rowHeader}>
          <span className={styles.rowHeaderTitle}>已配置供应商</span>
          <Button size="sm" icon="plus" onClick={() => setAddOpen(true)}>添加供应商</Button>
        </div>

        {providers.length === 0 ? (
          <div className={styles.emptyState}>暂无供应商，点击添加</div>
        ) : (
          <div className={styles.cardGrid}>
            {providers.map((p) => (
              <div key={p.id} className={styles.card}>
                <div className={`${styles.statusDot} ${p.is_healthy ? styles.statusHealthy : styles.statusUnhealthy}`} />
                <div className={styles.cardBody}>
                  <div className={styles.cardName}>{p.name}</div>
                  <div className={styles.cardMeta}>{p.model_id} · {p.base_url}</div>
                  <div className={styles.cardBadges}>
                    <Badge variant={protocolBadgeVariant(p.protocol)}>{p.protocol}</Badge>
                    <Badge variant="neutral">{p.scope}</Badge>
                    {p.is_default && <Badge variant="amber">默认</Badge>}
                  </div>
                </div>
                <div className={styles.cardActions}>
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={testingId === p.id}
                    onClick={() => handleTest(p.id)}
                  >
                    测试连接
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={deletingId === p.id}
                    onClick={() => setConfirmDeleteId(p.id)}
                  >
                    删除
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add provider modal */}
      <Modal open={addOpen} onClose={() => { setAddOpen(false); setForm(EMPTY_FORM); }} title="添加供应商" width={520}>
        <div className={styles.modalFields}>
          {presets.length > 0 && (
            <div className={styles.field}>
              <label className={styles.label}>预设</label>
              <select
                className={styles.select}
                defaultValue=""
                onChange={(e) => {
                  const preset = presets.find((pr) => pr.name === e.target.value);
                  if (preset) applyPreset(preset);
                }}
              >
                <option value="">— 选择预设 —</option>
                {presets.map((pr) => (
                  <option key={pr.name} value={pr.name}>{pr.name}</option>
                ))}
              </select>
            </div>
          )}
          <div className={styles.field}>
            <label className={styles.label}>名称 *</label>
            <input
              className={styles.input}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="My Provider"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>协议 *</label>
            <select
              className={styles.select}
              value={form.protocol}
              onChange={(e) => setForm((f) => ({ ...f, protocol: e.target.value as 'anthropic' | 'openai' }))}
            >
              <option value="anthropic">anthropic</option>
              <option value="openai">openai</option>
            </select>
          </div>
          <div className={styles.field}>
            <label className={styles.label}>API Key *</label>
            <input
              className={styles.input}
              type="password"
              value={form.api_key}
              onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
              placeholder="sk-..."
              autoComplete="off"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Base URL</label>
            <input
              className={styles.input}
              value={form.base_url}
              onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
              placeholder="https://api.anthropic.com"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Model ID *</label>
            <input
              className={styles.input}
              value={form.model_id}
              onChange={(e) => setForm((f) => ({ ...f, model_id: e.target.value }))}
              placeholder="claude-opus-4-5"
            />
          </div>
        </div>
        <div className={styles.modalFooter}>
          <Button variant="ghost" onClick={() => { setAddOpen(false); setForm(EMPTY_FORM); }}>取消</Button>
          <Button loading={saving} onClick={handleAdd}>添加</Button>
        </div>
      </Modal>

      <ConfirmModal
        open={confirmDeleteId !== null}
        title="确认删除"
        message="确认删除该供应商？此操作不可撤销。"
        confirmLabel="删除"
        danger
        loading={deletingId !== null}
        onConfirm={() => { if (confirmDeleteId) handleDelete(confirmDeleteId); }}
        onCancel={() => setConfirmDeleteId(null)}
      />
    </>
  );
}
