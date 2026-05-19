import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as api from '@/api/client';
import type { AuthProvidersResponse } from '@/api/types';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/Button/Button';
import { Icon } from '@/components/Icon/Icon';
import { AuthLayout } from './AuthLayout';
import styles from './LoginPage.module.css';

type LoginMode = 'password' | 'otp' | 'magic';

export function LoginPage() {
  const { login, loginWithToken } = useAuth();
  const navigate = useNavigate();

  const [mode, setMode] = useState<LoginMode>('password');

  // Password login
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);
  const [errMsg, setErrMsg] = useState('');

  // OTP login
  const [otpEmail, setOtpEmail] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [otpLoading, setOtpLoading] = useState(false);
  const [otpOk, setOtpOk] = useState('');
  const [otpErr, setOtpErr] = useState('');

  // Magic link
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

  function switchMode(m: LoginMode) {
    setMode(m);
    setErrMsg('');
    setOtpErr('');
    setOtpOk('');
    setMagicErr('');
    setMagicOk('');
  }

  // --- Password login ---
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

  // --- OTP login ---
  async function handleOtpRequest() {
    setOtpErr('');
    setOtpOk('');
    if (!otpEmail.trim()) { setOtpErr('请输入邮箱'); return; }
    setOtpLoading(true);
    try {
      await api.emailOtpRequest({ email: otpEmail.trim() });
      setOtpSent(true);
      setOtpOk('验证码已发送，请查收邮件');
    } catch (err) {
      const e = err as { message?: string };
      setOtpErr(e.message ?? '发送失败');
    }
    setOtpLoading(false);
  }

  async function handleOtpVerify() {
    setOtpErr('');
    if (!otpCode.trim()) { setOtpErr('请输入 6 位验证码'); return; }
    setOtpLoading(true);
    try {
      const resp = await api.emailOtpVerify({ email: otpEmail.trim(), code: otpCode.trim() });
      await loginWithToken(resp.access_token);
      navigate('/', { replace: true });
    } catch (err) {
      const e = err as { status?: number; message?: string };
      if (e.status === 401) setOtpErr('验证码错误或已过期');
      else setOtpErr(e.message ?? '验证失败');
    }
    setOtpLoading(false);
  }

  // --- Magic link ---
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

      {/* Mode tabs */}
      <div className={styles.modeTabs}>
        <button className={`${styles.modeTab} ${mode === 'password' ? styles.modeTabActive : ''}`} onClick={() => switchMode('password')}>密码</button>
        <button className={`${styles.modeTab} ${mode === 'otp' ? styles.modeTabActive : ''}`} onClick={() => switchMode('otp')}>验证码</button>
        <button className={`${styles.modeTab} ${mode === 'magic' ? styles.modeTabActive : ''}`} onClick={() => switchMode('magic')}>Magic Link</button>
      </div>

      {/* === Password mode === */}
      {mode === 'password' && (
        <div className={styles.fields}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-email">邮箱</label>
            <input id="login-email" ref={emailRef} className={styles.input} type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} onKeyDown={onKeyDown} />
          </div>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="login-password">密码</label>
            <div className={styles.inputWrap}>
              <input id="login-password" className={styles.input} type={showPw ? 'text' : 'password'} autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={onKeyDown} />
              <button type="button" className={styles.eyeBtn} onClick={() => setShowPw(v => !v)} tabIndex={-1} aria-label={showPw ? '隐藏密码' : '显示密码'}>
                <Icon name="eye" size={16} />
              </button>
            </div>
          </div>
          <div className={styles.forgotRow}>
            <a href="#" className={styles.forgotLink} onClick={e => { e.preventDefault(); }}>忘了密码?</a>
          </div>
          {errMsg && <div className={styles.errBox}>{errMsg}</div>}
          <Button className={styles.submitBtn} variant="primary" loading={loading} onClick={handleLogin}>登录</Button>
        </div>
      )}

      {/* === OTP mode === */}
      {mode === 'otp' && (
        <div className={styles.fields}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="otp-email">邮箱</label>
            <input id="otp-email" className={styles.input} type="email" autoComplete="email" value={otpEmail} onChange={e => { setOtpEmail(e.target.value); setOtpSent(false); setOtpOk(''); }} disabled={otpSent} />
          </div>
          {otpSent && (
            <div className={styles.field}>
              <label className={styles.label} htmlFor="otp-code">验证码</label>
              <input id="otp-code" className={styles.input} type="text" inputMode="numeric" maxLength={6} placeholder="6 位数字" value={otpCode} onChange={e => setOtpCode(e.target.value.replace(/\D/g, ''))} onKeyDown={e => { if (e.key === 'Enter') handleOtpVerify(); }} autoFocus />
            </div>
          )}
          {otpErr && <div className={styles.errBox}>{otpErr}</div>}
          {otpOk && <div className={styles.okBox}>{otpOk}</div>}
          {!otpSent ? (
            <Button className={styles.submitBtn} variant="primary" loading={otpLoading} onClick={handleOtpRequest}>发送验证码</Button>
          ) : (
            <div style={{ display: 'flex', gap: 8 }}>
              <Button className={styles.submitBtn} variant="primary" loading={otpLoading} onClick={handleOtpVerify}>验证登录</Button>
              <Button className={styles.ghostBtn} variant="ghost" onClick={() => { setOtpSent(false); setOtpOk(''); setOtpCode(''); }}>重新发送</Button>
            </div>
          )}
        </div>
      )}

      {/* === Magic Link mode === */}
      {mode === 'magic' && (
        <div className={styles.fields}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="magic-email">邮箱</label>
            <input id="magic-email" className={styles.input} type="email" autoComplete="email" value={magicEmail} onChange={e => { setMagicEmail(e.target.value); setMagicSent(false); }} disabled={magicSent} />
          </div>
          {magicErr && <div className={styles.errBox}>{magicErr}</div>}
          {magicOk && <div className={styles.okBox}>{magicOk}</div>}
          {!magicSent ? (
            <Button className={styles.submitBtn} variant="primary" loading={magicLoading} onClick={handleMagicRequest}>发送登录链接</Button>
          ) : (
            <Button className={styles.ghostBtn} variant="ghost" onClick={() => { setMagicSent(false); setMagicOk(''); setMagicErr(''); }}>重新发送</Button>
          )}
        </div>
      )}

      {/* Google OAuth */}
      {providers?.google && (
        <Button className={styles.ghostBtn} style={{ marginTop: 16 }} variant="ghost" icon="globe" onClick={handleGoogleLogin}>使用 Google 账号登录</Button>
      )}

      {/* Footer */}
      <p className={styles.footer}>
        还没有账号？
        <Link to="/register" className={styles.footerLink}>立即注册</Link>
      </p>
    </AuthLayout>
  );
}
