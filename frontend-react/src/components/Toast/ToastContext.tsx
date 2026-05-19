import { createContext, useContext, useState } from 'react';
import { uuid } from '@/utils/cn';
import type { ReactNode } from 'react';

export interface ToastItem {
  id: string;
  message: string;
  variant: 'info' | 'success' | 'error';
}

interface ToastContextValue {
  toasts: ToastItem[];
  addToast: (message: string, variant?: ToastItem['variant']) => void;
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  function addToast(message: string, variant: ToastItem['variant'] = 'info') {
    const id = uuid();
    setToasts((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => removeToast(id), 6000);
  }

  function removeToast(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside ToastProvider');
  return ctx;
}
