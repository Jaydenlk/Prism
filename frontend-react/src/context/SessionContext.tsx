import { createContext, useCallback, useEffect, useState, type ReactNode } from 'react';
import * as api from '@/api/client';
import type { Session, SessionListItem } from '@/api/types';
import { useAuth } from '@/hooks/useAuth';

interface SessionState {
  sessions: SessionListItem[];
  currentSessionId: string | null;
  loading: boolean;
  setCurrentSessionId: (id: string | null) => void;
  createSession: (opts?: Record<string, unknown>) => Promise<Session>;
  deleteSession: (id: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
}

export const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshSessions = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const data = await api.sessions.list();
      setSessions(data.items);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) refreshSessions();
  }, [user, refreshSessions]);

  const createSession = useCallback(async (opts?: Record<string, unknown>) => {
    const session = await api.sessions.create(opts ?? {});
    setSessions((prev) => [
      { id: session.id, title: session.title, status: session.status, is_pinned: session.is_pinned, last_message_preview: session.last_message_preview, updated_at: session.updated_at },
      ...prev,
    ]);
    setCurrentSessionId(session.id);
    return session;
  }, []);

  const deleteSession = useCallback(async (id: string) => {
    await api.sessions.delete(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (currentSessionId === id) setCurrentSessionId(null);
  }, [currentSessionId]);

  return (
    <SessionContext.Provider value={{
      sessions, currentSessionId, loading,
      setCurrentSessionId, createSession, deleteSession, refreshSessions,
    }}>
      {children}
    </SessionContext.Provider>
  );
}
