import type { ReactNode } from 'react';
import { PrismGlyph, PrismMark } from '@/components/Icon/Icon';
import styles from './AuthLayout.module.css';

interface AuthLayoutProps {
  children: ReactNode;
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className={styles.wrap}>
      {/* Left brand panel — desktop only */}
      <div className={styles.left}>
        <div className={styles.leftGlyph}>
          <PrismGlyph size={420} />
        </div>
        <div className={styles.leftContent}>
          <PrismMark size={26} />
          <p className={styles.leftBrand}>Prism 棱镜</p>
          <p className={styles.leftTagline}>
            让大模型变得可靠、可治理、可扩展 —— 而不是只会幻觉的聊天框。
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className={styles.right}>
        {/* Mobile logo */}
        <div className={styles.mobileLogo}>
          <PrismMark size={20} />
          <span>Prism 棱镜</span>
        </div>

        <div className={styles.card}>
          {children}
        </div>
      </div>
    </div>
  );
}
