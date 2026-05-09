import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react';
import * as api from '@/api/client';
import type { User } from '@/api/types';

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (params: { email: string; username: string; password: string; invite_code?: string }) => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(api.currentUser());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (api.isAuthenticated()) {
      api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
    const handler = () => { setUser(null); setLoading(false); };
    window.addEventListener('prism:unauthorized', handler);
    return () => window.removeEventListener('prism:unauthorized', handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    setUser(result.user);
  }, []);

  const register = useCallback(async (params: { email: string; username: string; password: string; invite_code?: string }) => {
    await api.register(params);
  }, []);

  const logoutFn = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout: logoutFn }}>
      {children}
    </AuthContext.Provider>
  );
}
