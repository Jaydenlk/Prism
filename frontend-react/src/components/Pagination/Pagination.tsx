import { Button } from '@/components/Button/Button';
import styles from './Pagination.module.css';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;
  return (
    <div className={styles.pagination}>
      <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => onPageChange(Math.max(1, page - 1))}>上一页</Button>
      <span className={styles.info}>{page} / {totalPages}</span>
      <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>下一页</Button>
    </div>
  );
}
