import { useState, useEffect } from 'react';
import * as api from '@/api/client';
import type { IMChannel, IMBinding, PairingCodeResponse } from '@/api/types';
import { useToast } from '@/components/Toast/ToastContext';
import { Button } from '@/components/Button/Button';
import { Badge } from '@/components/Badge/Badge';
import { Modal } from '@/components/Modal/Modal';
import { ConfirmModal } from '@/components/ConfirmModal/ConfirmModal';
import { Spinner } from '@/components/Spinner/Spinner';
import styles from './SettingsPage.module.css';

const PLATFORM_ICONS: Record<string, string> = {
  telegram: '✈',
  wechat: '💬',
  slack: '#',
  discord: '▶',
};

const DEFAULT_PLATFORM_ICON = '📡';

function platformIcon(channel: string): string {
  return PLATFORM_ICONS[channel.toLowerCase()] ?? DEFAULT_PLATFORM_ICON;
}

export function ImTab() {
  const { addToast } = useToast();
  const [channels, setChannels] = useState<IMChannel[]>([]);
  const [bindings, setBindings] = useState<IMBinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [pairingChannel, setPairingChannel] = useState('');
  const [pairingResult, setPairingResult] = useState<PairingCodeResponse | null>(null);
  const [pairingLoading, setPairingLoading] = useState(false);
  const [pairModalOpen, setPairModalOpen] = useState(false);
  const [unbindingId, setUnbindingId] = useState<string | null>(null);
  const [confirmUnbindId, setConfirmUnbindId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const [ch, bn] = await Promise.all([api.im.listChannels(), api.im.listBindings()]);
        if (!cancelled) {
          setChannels(ch);
          setBindings(bn);
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

  async function handleGeneratePairingCode() {
    if (!pairingChannel) {
      addToast('请选择频道', 'error');
      return;
    }
    setPairingLoading(true);
    try {
      const result = await api.im.generatePairingCode({ channel: pairingChannel });
      setPairingResult(result);
    } catch (err) {
      addToast(err instanceof Error ? err.message : '生成失败', 'error');
    } finally {
      setPairingLoading(false);
    }
  }

  async function handleUnbind(id: string) {
    setUnbindingId(id);
    try {
      await api.im.unbind(id);
      setBindings((prev) => prev.filter((b) => b.id !== id));
      addToast('已解绑', 'success');
    } catch (err) {
      addToast(err instanceof Error ? err.message : '解绑失败', 'error');
    } finally {
      setUnbindingId(null);
      setConfirmUnbindId(null);
    }
  }

  function openPairModal() {
    setPairingResult(null);
    setPairingChannel(channels.find((c) => c.is_enabled)?.channel ?? '');
    setPairModalOpen(true);
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
      {/* Channels */}
      <div className={styles.section}>
        <div className={styles.rowHeader}>
          <span className={styles.rowHeaderTitle}>即时通讯频道</span>
          <Button size="sm" icon="link" onClick={openPairModal}>生成配对码</Button>
        </div>

        {channels.length === 0 ? (
          <div className={styles.emptyState}>暂无配置频道</div>
        ) : (
          <>
            {channels.map((ch) => (
              <div key={ch.id} className={styles.channelCard}>
                <div className={styles.channelIcon}>{platformIcon(ch.channel)}</div>
                <span className={styles.channelName}>{ch.channel}</span>
                <Badge variant={ch.is_enabled ? 'teal' : 'neutral'}>
                  {ch.is_enabled ? '已启用' : '已禁用'}
                </Badge>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Bindings */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>用户绑定</div>
        {bindings.length === 0 ? (
          <div className={styles.emptyState}>暂无绑定用户</div>
        ) : (
          <div className={styles.cardGrid}>
            {bindings.map((b) => (
              <div key={b.id} className={styles.card}>
                <div className={styles.cardBody}>
                  <div className={styles.cardName}>{b.display_name ?? b.platform_user_id}</div>
                  <div className={styles.cardMeta}>{b.channel} · {b.platform_chat_id}</div>
                  <div className={styles.cardBadges}>
                    <Badge variant="neutral">{b.channel}</Badge>
                  </div>
                </div>
                <div className={styles.cardActions}>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={unbindingId === b.id}
                    onClick={() => setConfirmUnbindId(b.id)}
                  >
                    解绑
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pair modal */}
      <Modal
        open={pairModalOpen}
        onClose={() => { setPairModalOpen(false); setPairingResult(null); }}
        title="生成配对码"
        width={440}
      >
        <div className={styles.modalFields}>
          <div className={styles.field}>
            <label className={styles.label}>频道</label>
            <select
              className={styles.select}
              value={pairingChannel}
              onChange={(e) => setPairingChannel(e.target.value)}
            >
              {channels.filter((c) => c.is_enabled).map((c) => (
                <option key={c.id} value={c.channel}>{c.channel}</option>
              ))}
            </select>
          </div>
          {pairingResult ? (
            <>
              <div className={styles.pairingCode}>{pairingResult.pairing_code}</div>
              <div className={styles.pairingExpiry}>
                有效期至 {new Date(pairingResult.expires_at).toLocaleString()}
              </div>
            </>
          ) : (
            <Button loading={pairingLoading} onClick={handleGeneratePairingCode}>
              生成配对码
            </Button>
          )}
        </div>
      </Modal>

      <ConfirmModal
        open={confirmUnbindId !== null}
        title="确认解绑"
        message="确认解绑该用户？解绑后需重新配对。"
        confirmLabel="解绑"
        danger
        loading={unbindingId !== null}
        onConfirm={() => { if (confirmUnbindId) handleUnbind(confirmUnbindId); }}
        onCancel={() => setConfirmUnbindId(null)}
      />
    </>
  );
}
