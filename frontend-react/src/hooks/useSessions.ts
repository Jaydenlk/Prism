import { useContext } from 'react';
import { SessionContext } from '@/context/SessionContext';

export function useSessions() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSessions must be inside SessionProvider');
  return ctx;
}
