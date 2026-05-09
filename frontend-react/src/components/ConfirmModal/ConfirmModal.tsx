import { Modal } from '@/components/Modal/Modal';
import { Button } from '@/components/Button/Button';

interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmModal({ open, title, message, confirmLabel = '确认', danger, loading, onConfirm, onCancel }: ConfirmModalProps) {
  return (
    <Modal open={open} onClose={onCancel} title={title} width={400}>
      <p style={{ marginBottom: 20, color: 'var(--ink-2)' }}>{message}</p>
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onCancel}>取消</Button>
        <Button variant={danger ? 'danger' : 'primary'} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </Modal>
  );
}
