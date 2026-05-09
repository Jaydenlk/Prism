import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from '@/context/AuthContext';
import { ThemeProvider } from '@/context/ThemeContext';
import { SessionProvider } from '@/context/SessionContext';
import { ToastProvider } from '@/components/Toast/ToastContext';
import { Toast } from '@/components/Toast/Toast';
import { AppLayout } from '@/components/Layout/AppLayout';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { LoadingPage } from '@/components/LoadingPage';
import { useAuth } from '@/hooks/useAuth';
import { LoginPage } from '@/pages/Auth/LoginPage';
import { RegisterPage } from '@/pages/Auth/RegisterPage';
import type { ReactNode } from 'react';

const ChatPage = lazy(() => import('@/pages/Chat/ChatPage').then(m => ({ default: m.ChatPage })));
const SessionsPage = lazy(() => import('@/pages/Sessions/SessionsPage').then(m => ({ default: m.SessionsPage })));
const SettingsPage = lazy(() => import('@/pages/Settings/SettingsPage').then(m => ({ default: m.SettingsPage })));
const UsagePage = lazy(() => import('@/pages/Usage/UsagePage').then(m => ({ default: m.UsagePage })));
const SkillsPage = lazy(() => import('@/pages/Skills/SkillsPage').then(m => ({ default: m.SkillsPage })));
const PluginBuilderPage = lazy(() => import('@/pages/Plugins/PluginBuilderPage').then(m => ({ default: m.PluginBuilderPage })));
const ObsPage = lazy(() => import('@/pages/Observability/ObsPage').then(m => ({ default: m.ObsPage })));
const AdminLayout = lazy(() => import('@/pages/Admin/AdminLayout').then(m => ({ default: m.AdminLayout })));
const AdminDashboard = lazy(() => import('@/pages/Admin/AdminDashboard').then(m => ({ default: m.AdminDashboard })));
const UsersPage = lazy(() => import('@/pages/Admin/UsersPage').then(m => ({ default: m.UsersPage })));
const AuditPage = lazy(() => import('@/pages/Admin/AuditPage').then(m => ({ default: m.AuditPage })));
const InvitesPage = lazy(() => import('@/pages/Admin/InvitesPage').then(m => ({ default: m.InvitesPage })));

function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <LoadingPage />
    </div>
  );
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PageSuspense({ children }: { children: ReactNode }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingPage />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<AuthGuard><AppLayout /></AuthGuard>}>
        <Route index element={<PageSuspense><ChatPage /></PageSuspense>} />
        <Route path="sessions" element={<PageSuspense><SessionsPage /></PageSuspense>} />
        <Route path="settings" element={<PageSuspense><SettingsPage /></PageSuspense>} />
        <Route path="usage" element={<PageSuspense><UsagePage /></PageSuspense>} />
        <Route path="skills" element={<PageSuspense><SkillsPage /></PageSuspense>} />
        <Route path="plugins" element={<PageSuspense><PluginBuilderPage /></PageSuspense>} />
        <Route path="admin" element={<PageSuspense><AdminLayout /></PageSuspense>}>
          <Route index element={<PageSuspense><AdminDashboard /></PageSuspense>} />
          <Route path="users" element={<PageSuspense><UsersPage /></PageSuspense>} />
          <Route path="audit" element={<PageSuspense><AuditPage /></PageSuspense>} />
          <Route path="invites" element={<PageSuspense><InvitesPage /></PageSuspense>} />
        </Route>
        <Route path="observability" element={<PageSuspense><ObsPage /></PageSuspense>} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <ErrorBoundary>
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
    </ErrorBoundary>
  );
}
