import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ThemeProvider } from '@/context/ThemeContext';
import { SessionProvider } from '@/context/SessionContext';
import { ToastProvider } from '@/components/Toast/ToastContext';
import { Toast } from '@/components/Toast/Toast';
import { AppLayout } from '@/components/Layout/AppLayout';
import { useAuth } from '@/hooks/useAuth';
import { Placeholder } from '@/pages/Placeholder';
import { LoginPage } from '@/pages/Auth/LoginPage';
import { RegisterPage } from '@/pages/Auth/RegisterPage';
import { ChatPage } from '@/pages/Chat/ChatPage';
import { SessionsPage } from '@/pages/Sessions/SessionsPage';
import { UsagePage } from '@/pages/Usage/UsagePage';
import { ObsPage } from '@/pages/Observability/ObsPage';
import { SettingsPage } from '@/pages/Settings/SettingsPage';
import { SkillsPage } from '@/pages/Skills/SkillsPage';
import { PluginBuilderPage } from '@/pages/Plugins/PluginBuilderPage';
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
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<AuthGuard><AppLayout /></AuthGuard>}>
        <Route index element={<ChatPage />} />
        <Route path="sessions" element={<SessionsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="usage" element={<UsagePage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="plugins" element={<PluginBuilderPage />} />
        <Route path="admin/*" element={<Placeholder name="管理" />} />
        <Route path="observability" element={<ObsPage />} />
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
