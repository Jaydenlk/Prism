import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '@/api/client';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/Button/Button';
import { Icon } from '@/components/Icon/Icon';
import { AuthLayout } from './AuthLayout';
import styles from './RegisterPage.module.css';

export function RegisterPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errMsg, setErrMsg] = useState('');

  const usernameRef = useRef<HTMLInputElement>(null);

  // Client-side validation before hitting the API
  function validate(): string {
    if (!username.trim()) return '用户名不能为空';
    if (!email.trim()) return '邮箱不能为空';
    const emailOk = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
    if (!emailOk) return '邮箱格式不正确';
    if (password.length < 8) return '密码至少 8 位';
    return '';
  }

  async function handleRegister() {
    setErrMsg('');
    const validErr = validate();
    if (validErr) { setErrMsg(validErr); return; }

    setLoading(true);
    try {
      await api.register({
        email: email.trim(),
        username: username.trim(),
        password,
        invite_code: inviteCode.trim() || undefined,
      });
      // Auto-login after successful registration
      await login(email.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      const e = err as { status?: number; message?: string };
      if (e.status === 409) setErrMsg('邮箱或用户名已注册');
      else if (e.status === 400) setErrMsg(e.message ?? '邀请码无效');
      else setErrMsg(e.message ?? '注册失败');
    }
    setLoading(false);
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleRegister();
  };

  return (
    <AuthLayout>
      <h1 className={styles.title}>加入 Prism</h1>

      <div className={styles.fields}>
        {/* Username */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="reg-username">用户名</label>
          <input
            id="reg-username"
            ref={usernameRef}
            className={styles.input}
            type="text"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            onKeyDown={onKeyDown}
            autoFocus
          />
        </div>

        {/* Email */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="reg-email">邮箱</label>
          <input
            id="reg-email"
            className={styles.input}
            type="email"
            autoComplete="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={onKeyDown}
          />
        </div>

        {/* Password */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="reg-password">密码</label>
          <div className={styles.inputWrap}>
            <input
              id="reg-password"
              className={styles.input}
              type={showPw ? 'text' : 'password'}
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button
              type="button"
              className={styles.eyeBtn}
              onClick={() => setShowPw(v => !v)}
              tabIndex={-1}
              aria-label={showPw ? '隐藏密码' : '显示密码'}
            >
              <Icon name="eye" size={16} />
            </button>
          </div>
          {password.length > 0 && password.length < 8 && (
            <span className={styles.fieldError}>密码至少 8 位</span>
          )}
        </div>

        {/* Invite code */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="reg-invite">邀请码</label>
          <input
            id="reg-invite"
            className={styles.input}
            type="text"
            placeholder="PRISM-XXXXXXXX"
            value={inviteCode}
            onChange={e => setInviteCode(e.target.value)}
            onKeyDown={onKeyDown}
          />
          <span className={styles.helper}>如需邀请码请联系管理员</span>
        </div>

        {/* Global error */}
        {errMsg && <div className={styles.errBox}>{errMsg}</div>}

        {/* Submit */}
        <Button
          className={styles.submitBtn}
          variant="primary"
          loading={loading}
          onClick={handleRegister}
        >
          创建账号
        </Button>
      </div>

      {/* Footer */}
      <p className={styles.footer}>
        已有账号？
        <Link to="/login" className={styles.footerLink}>回去登录</Link>
      </p>
    </AuthLayout>
  );
}
