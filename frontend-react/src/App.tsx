import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ThemeProvider } from '@/context/ThemeContext';
import { SessionProvider } from '@/context/SessionContext';
import { ToastProvider } from '@/components/Toast/ToastContext';
import { Toast } from '@/components/Toast/Toast';
import { AppLayout } from '@/components/Layout/AppLayout';
import { useAuth } from '@/hooks/useAuth';
import { Placeholder } from '@/pages/Placeholder';
import type { ReactNode } from 'react';

function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      Loading...
    </div>
  );
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Placeholder name="Login" />} />
      <Route path="/register" element={<Placeholder name="Register" />} />
      <Route element={<AuthGuard><AppLayout /></AuthGuard>}>
        <Route index element={<Placeholder name="对话" />} />
        <Route path="sessions" element={<Placeholder name="会话" />} />
        <Route path="settings" element={<Placeholder name="设置" />} />
        <Route path="usage" element={<Placeholder name="用量" />} />
        <Route path="skills" element={<Placeholder name="技能市场" />} />
        <Route path="plugins" element={<Placeholder name="插件构建" />} />
        <Route path="admin/*" element={<Placeholder name="管理" />} />
        <Route path="observability" element={<Placeholder name="可观测性" />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <ToastProvider>
          <Toast />
          <AuthProvider>
            <SessionProvider>
              <AppRoutes />
            </SessionProvider>
          </AuthProvider>
        </ToastProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
