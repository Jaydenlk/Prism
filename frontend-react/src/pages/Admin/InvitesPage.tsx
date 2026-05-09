import { useState, useEffect, useCallback } from 'react';
import * as api from '@/api/client';
import type { InviteCode } from '@/api/types';
import { Badge } from '@/components/Badge/Badge';
import { Button } from '@/components/Button/Button';
import { Modal } from '@/components/Modal/Modal';
import { useToast } from '@/components/Toast/ToastContext';
import styles from './InvitesPage.module.css';

function statusBadge(code: InviteCode) {
  if (!code.is_valid) {
    return code.used_count >= code.max_uses
      ? <Badge variant="neutral">已用完</Badge>
      : <Badge variant="rust">已撤销</Badge>;
  }
  return <Badge variant="teal">有效</Badge>;
}

export function InvitesPage() {
  const { addToast } = useToast();
  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [maxUses, setMaxUses] = useState(5);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<InviteCode | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');

    api.admin.listInviteCodes()
      .then(data => {
        if (!cancelled) setCodes(data);
      })
      .catch((e: Error) => {
        if (!cancelled) setErr(e.message ?? '加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    return load();
  }, [load]);

  async function handleCreate() {
    setCreating(true);
    try {
      const code = await api.admin.createInviteCode({ max_uses: maxUses });
      setCodes(prev => [code, ...prev]);
      setShowCreate(false);
      setMaxUses(5);
      addToast('邀请码已生成', 'success');
    } catch (e) {
      addToast((e as Error).message ?? '生成失败', 'error');
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(code: InviteCode) {
    setRevoking(code.id);
    setConfirmRevoke(null);
    try {
      await api.admin.revokeInviteCode(code.id);
      addToast(`邀请码 ${code.code} 已撤销`, 'success');
      load();
    } catch (e) {
      addToast((e as Error).message ?? '撤销失败', 'error');
    } finally {
      setRevoking(null);
    }
  }

  function copyCode(code: string) {
    navigator.clipboard.writeText(code).then(() => {
      addToast('已复制', 'success');
    }).catch(() => {
      addToast('复制失败', 'error');
    });
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>邀请码管理</h1>
        <Button size="sm" icon="plus" onClick={() => setShowCreate(true)}>
          生成邀请码
        </Button>
      </div>

      {err && <div className={styles.errorState}>加载失败: {err}</div>}

      {loading ? (
        <div className={styles.loadingState}>正在加载…</div>
      ) : codes.length === 0 ? (
        <div className={styles.emptyState}>暂无邀请码</div>
      ) : (
        <div className={styles.cardList}>
          {codes.map(code => (
            <div key={code.id} className={styles.card}>
              <div className={styles.cardTop}>
                <span className={styles.code}>{code.code}</span>
                <button
                  className={styles.copyBtn}
                  onClick={() => copyCode(code.code)}
                  title="复制"
                >
                  复制
                </button>
                {statusBadge(code)}
              </div>
              <div className={styles.cardMeta}>
                <span>使用: {code.used_count} / {code.max_uses}</span>
                <span>创建: {new Date(code.created_at).toLocaleDateString('zh-CN')}</span>
                {code.expires_at && (
                  <span>到期: {new Date(code.expires_at).toLocaleDateString('zh-CN')}</span>
                )}
              </div>
              {code.is_valid && (
                <div className={styles.cardActions}>
                  <Button
                    variant="danger"
                    size="sm"
                    loading={revoking === code.id}
                    onClick={() => setConfirmRevoke(code)}
                  >
                    撤销
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Create modal */}
      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="生成邀请码" width={360}>
        <div className={styles.createForm}>
          <label className={styles.formLabel}>最大使用次数</label>
          <input
            type="number"
            className={styles.formInput}
            min={1}
            max={100}
            value={maxUses}
            onChange={e => setMaxUses(Math.max(1, Number(e.target.value)))}
          />
          <div className={styles.formActions}>
            <Button variant="ghost" size="sm" onClick={() => setShowCreate(false)}>取消</Button>
            <Button size="sm" loading={creating} onClick={handleCreate}>生成</Button>
          </div>
        </div>
      </Modal>

      {/* Confirm revoke modal */}
      <Modal
        open={confirmRevoke !== null}
        onClose={() => setConfirmRevoke(null)}
        title="确认撤销"
        width={360}
      >
        <div className={styles.confirmBody}>
          <p>确认撤销邀请码 <code className={styles.confirmCode}>{confirmRevoke?.code}</code>？此操作不可逆。</p>
          <div className={styles.formActions}>
            <Button variant="ghost" size="sm" onClick={() => setConfirmRevoke(null)}>取消</Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => confirmRevoke && handleRevoke(confirmRevoke)}
            >
              确认撤销
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
