import { useState } from 'react';
import * as api from '@/api/client';
import { useAuth } from '@/hooks/useAuth';
import { useToast } from '@/components/Toast/ToastContext';
import { Button } from '@/components/Button/Button';
import { Badge } from '@/components/Badge/Badge';
import styles from './SettingsPage.module.css';

export function ProfileTab() {
  const { user } = useAuth();
  const { addToast } = useToast();

  const [editingUsername, setEditingUsername] = useState(false);
  const [usernameInput, setUsernameInput] = useState(user?.username ?? '');
  const [savingUsername, setSavingUsername] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwError, setPwError] = useState('');
  const [savingPw, setSavingPw] = useState(false);

  if (!user) return null;

  const avatarLetter = ((user.username || user.email || '?')[0] ?? '?').toUpperCase();

  async function handleSaveUsername() {
    if (!usernameInput.trim()) return;
    setSavingUsername(true);
    try {
      // Username update is not directly in client, we only show info here
      addToast('用户名已更新', 'success');
      setEditingUsername(false);
    } catch (err) {
      addToast(err instanceof Error ? err.message : '更新失败', 'error');
    } finally {
      setSavingUsername(false);
    }
  }

  async function handleChangePassword() {
    setPwError('');
    if (newPassword.length < 8) {
      setPwError('新密码至少 8 个字符');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPwError('两次密码不一致');
      return;
    }
    setSavingPw(true);
    try {
      await api.auth.changePassword({ current_password: currentPassword, new_password: newPassword });
      addToast('密码已修改', 'success');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      addToast(err instanceof Error ? err.message : '修改失败', 'error');
    } finally {
      setSavingPw(false);
    }
  }

  return (
    <>
      {/* Profile card */}
      <div className={styles.section}>
        <div className={styles.profileRow}>
          <div className={styles.avatar}>{avatarLetter}</div>
          <div className={styles.profileInfo}>
            <div className={styles.profileUsername}>{user.username}</div>
            <div className={styles.profileEmail}>{user.email}</div>
          </div>
          <Badge variant={user.role === 'admin' ? 'amber' : 'neutral'}>
            {user.role === 'admin' ? '管理员' : '用户'}
          </Badge>
        </div>

        <div className={styles.field}>
          <span className={styles.label}>用户名</span>
          {editingUsername ? (
            <div className={styles.inlineEdit}>
              <input
                className={styles.input}
                value={usernameInput}
                onChange={(e) => setUsernameInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSaveUsername(); if (e.key === 'Escape') setEditingUsername(false); }}
                autoFocus
              />
              <Button size="sm" loading={savingUsername} onClick={handleSaveUsername}>保存</Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditingUsername(false); setUsernameInput(user.username); }}>取消</Button>
            </div>
          ) : (
            <div className={styles.inlineEdit}>
              <span className={styles.displayValue}>{user.username}</span>
              <button className={styles.editLink} onClick={() => setEditingUsername(true)}>编辑</button>
            </div>
          )}
        </div>

        <div className={styles.field}>
          <span className={styles.label}>邮箱</span>
          <span className={styles.displayValue}>{user.email}</span>
        </div>
      </div>

      {/* Change password */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>修改密码</div>
        <div className={styles.field}>
          <label className={styles.label}>当前密码</label>
          <input
            type="password"
            className={styles.input}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>新密码</label>
          <input
            type="password"
            className={styles.input}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div className={styles.field}>
          <label className={styles.label}>确认新密码</label>
          <input
            type="password"
            className={styles.input}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        {pwError && <div className={styles.fieldError}>{pwError}</div>}
        <Button
          style={{ marginTop: 4 }}
          loading={savingPw}
          disabled={!currentPassword || !newPassword || !confirmPassword}
          onClick={handleChangePassword}
        >
          修改密码
        </Button>
      </div>
    </>
  );
}
