import styles from './Skeleton.module.css';

interface SkeletonProps {
  width?: string;
  height?: string;
  borderRadius?: string;
}

export function Skeleton({ width = '100%', height = '1em', borderRadius = '4px' }: SkeletonProps) {
  return <div className={styles.skeleton} style={{ width, height, borderRadius }} />;
}

export function SkeletonLines({ count = 3 }: { count?: number }) {
  return (
    <div className={styles.lines}>
      {Array.from({ length: count }, (_, i) => (
        <Skeleton key={i} width={i === count - 1 ? '60%' : '100%'} height="0.9em" />
      ))}
    </div>
  );
}
