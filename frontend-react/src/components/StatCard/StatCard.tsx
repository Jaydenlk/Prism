import { cn } from '@/utils/cn';
import styles from './StatCard.module.css';

interface StatCardProps {
  label: string;
  value?: string;
  featured?: boolean;
  children?: React.ReactNode;
  className?: string;
}

export function StatCard({ label, value, featured, children, className }: StatCardProps) {
  return (
    <div className={cn(styles.card, featured && styles.featured, className)}>
      <div className={styles.label}>{label}</div>
      {value ? <div className={styles.value}>{value}</div> : children}
    </div>
  );
}
