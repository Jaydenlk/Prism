import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '@/api/client';
import type { AuthProvidersResponse } from '@/api/types';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/Button/Button';
import { Icon } from '@/components/Icon/Icon';
import { AuthLayout } from './AuthLayout';
import styles from './LoginPage.module.css';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errMsg, setErrMsg] = useState('');

  const [magicEmail, setMagicEmail] = useState('');
  const [magicLoading, setMagicLoading] = useState(false);
  const [magicSent, setMagicSent] = useState(false);
  const [magicOk, setMagicOk] = useState('');
  const [magicErr, setMagicErr] = useState('');

  const [providers, setProviders] = useState<AuthProvidersResponse | null>(null);

  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    emailRef.current?.focus();
    api.authProviders().then(setProviders).catch(() => {});
  }, []);

  async function handleLogin() {
    setErrMsg('');
    if (!email.trim() || !password.trim()) {
      setErrMsg('邮箱和密码不能为空');
      return;
    }
    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate('/', { replace: true });
    } catch (err) {
      const e = err as { status?: number; message?: string };
      if (e.status === 401) setErrMsg('邮箱或密码错误');
      else setErrMsg(e.message ?? '登录失败');
    }
    setLoading(false);
  }

  async function handleMagicRequest() {
    setMagicErr('');
    setMagicOk('');
    if (!magicEmail.trim()) { setMagicErr('请输入邮箱'); return; }
    setMagicLoading(true);
    try {
      await api.emailMagicRequest({ email: magicEmail.trim() });
      setMagicSent(true);
      setMagicOk('如果邮箱已注册，Magic Link 已发出，请查收邮件。');
    } catch (err) {
      const e = err as { message?: string };
      setMagicErr(e.message ?? '请求失败');
    }
    setMagicLoading(false);
  }

  function handleGoogleLogin() {
    window.location.href = '/api/v1/auth/google/authorize';
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleLogin();
  };

  return (
    <AuthLayout>
      <h1 className={styles.title}>回到 Prism</h1>

      <div className={styles.fields}>
        {/* Email */}
        <div className={styles.field}>
          <label className={styles.label} htmlFor="login-email">邮箱</label>
          <input
            id="login-email"
            ref={emailRef}
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
          <label className={styles.label} htmlFor="login-password">密码</label>
          <div className={styles.inputWrap}>
            <input
              id="login-password"
              className={styles.input}
              type={showPw ? 'text' : 'password'}
              autoComplete="current-password"
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
        </div>

        {/* Forgot password */}
        <div className={styles.forgotRow}>
          <a href="#" className={styles.forgotLink} onClick={e => { e.preventDefault(); /* TODO: forgot password modal */ }}>
            忘了密码?
          </a>
        </div>

        {/* Global error */}
        {errMsg && <div className={styles.errBox}>{errMsg}</div>}

        {/* Submit */}
        <Button
          className={styles.submitBtn}
          variant="primary"
          loading={loading}
          onClick={handleLogin}
        >
          登录
        </Button>
      </div>

      {/* Magic link divider + section */}
      {(providers == null || providers.email_magic) && (
        <>
          <div className={styles.divider}>或者</div>
          <div className={styles.magicSection}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="magic-email">邮箱</label>
              <input
                id="magic-email"
                className={styles.input}
                type="email"
                autoComplete="email"
                value={magicEmail}
                onChange={e => { setMagicEmail(e.target.value); setMagicSent(false); }}
                onKeyDown={e => { if (e.key === 'Enter') handleMagicRequest(); }}
                disabled={magicSent}
              />
            </div>
            {magicErr && <div className={styles.errBox}>{magicErr}</div>}
            {magicOk && <div className={styles.okBox}>{magicOk}</div>}
            {!magicSent ? (
              <Button
                className={styles.ghostBtn}
                variant="ghost"
                loading={magicLoading}
                onClick={handleMagicRequest}
              >
                发送登录链接
              </Button>
            ) : (
              <Button
                className={styles.ghostBtn}
                variant="ghost"
                onClick={() => { setMagicSent(false); setMagicOk(''); setMagicErr(''); }}
              >
                重新发送
              </Button>
            )}
          </div>
        </>
      )}

      {/* Google OAuth */}
      {providers?.google && (
        <Button
          className={styles.ghostBtn}
          style={{ marginTop: 10 }}
          variant="ghost"
          icon="globe"
          onClick={handleGoogleLogin}
        >
          使用 Google 账号登录
        </Button>
      )}

      {/* Footer */}
      <p className={styles.footer}>
        还没有账号？
        <Link to="/register" className={styles.footerLink}>立即注册</Link>
      </p>
    </AuthLayout>
  );
}
