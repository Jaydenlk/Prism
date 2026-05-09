import { createPortal } from 'react-dom';
import type { IconName } from '../Icon/Icon';
import { Icon } from '../Icon/Icon';
import { useToast } from './ToastContext';
import type { ToastItem } from './ToastContext';
import styles from './Toast.module.css';

const variantIcon: Record<ToastItem['variant'], IconName> = {
  info:    'info',
  success: 'check',
  error:   'alert',
};

const variantColor: Record<ToastItem['variant'], string> = {
  info:    'var(--amber)',
  success: 'var(--teal)',
  error:   'var(--rust)',
};

export function Toast() {
  const { toasts, removeToast } = useToast();

  if (toasts.length === 0) return null;

  return createPortal(
    <div className={styles.stack} role="status" aria-live="polite" aria-atomic="false">
      {toasts.map((toast) => (
        <div key={toast.id} className={`${styles.toast} ${styles[toast.variant]}`}>
          <span className={styles.icon} style={{ color: variantColor[toast.variant] }}>
            <Icon name={variantIcon[toast.variant]} size={15} />
          </span>
          <span className={styles.message}>{toast.message}</span>
          <button
            className={styles.closeBtn}
            onClick={() => removeToast(toast.id)}
            aria-label="Dismiss"
          >
            <Icon name="close" size={12} />
          </button>
        </div>
      ))}
    </div>,
    document.body
  );
}
