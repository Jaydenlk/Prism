import { useTheme } from '@/hooks/useTheme';
import styles from './SettingsPage.module.css';

type ThemeOption = 'light' | 'dark';
type DensityOption = 'comfortable' | 'compact' | 'spacious';

const THEME_OPTIONS: Array<{ value: ThemeOption; label: string }> = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
];

const DENSITY_OPTIONS: Array<{ value: DensityOption; label: string }> = [
  { value: 'comfortable', label: '舒适' },
  { value: 'compact', label: '紧凑' },
  { value: 'spacious', label: '宽松' },
];

export function PreferencesTab() {
  const { theme, density, setTheme, setDensity } = useTheme();

  return (
    <>
      <div className={styles.section}>
        <div className={styles.sectionTitle}>外观</div>
        <div className={styles.field}>
          <span className={styles.label}>主题</span>
          <div className={styles.segmented}>
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`${styles.segmentBtn} ${theme === opt.value ? styles.segmentActive : ''}`}
                onClick={() => setTheme(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.field}>
          <span className={styles.label}>密度</span>
          <div className={styles.segmented}>
            {DENSITY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`${styles.segmentBtn} ${density === opt.value ? styles.segmentActive : ''}`}
                onClick={() => setDensity(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>语言</div>
        <div className={styles.field}>
          <span className={styles.label}>界面语言</span>
          <select className={styles.select} value="zh" disabled>
            <option value="zh">中文（简体）</option>
          </select>
        </div>
      </div>
    </>
  );
}
