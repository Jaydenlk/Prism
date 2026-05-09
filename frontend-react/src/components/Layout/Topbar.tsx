import { Icon } from '@/components/Icon/Icon';
import { Dropdown } from '@/components/Dropdown/Dropdown';
import { useTheme } from '@/hooks/useTheme';
import { useAuth } from '@/hooks/useAuth';
import styles from './Topbar.module.css';

interface TopbarProps {
  title: string;
  onMenuClick: () => void;
}

export function Topbar({ title, onMenuClick }: TopbarProps) {
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();

  const initials = user?.username ? (user.username[0]?.toUpperCase() ?? 'U') : 'U';

  return (
    <div className={styles.topbar}>
      <button className={styles.menuBtn} onClick={onMenuClick} aria-label="Open menu">
        <Icon name="menu" size={16} />
      </button>

      <div className={styles.title}>{title}</div>

      <div className={styles.right}>
        <button
          className={styles.iconBtn}
          onClick={toggleTheme}
          aria-label={theme === 'light' ? '切换深色模式' : '切换浅色模式'}
        >
          <Icon name={theme === 'light' ? 'eye' : 'sparkle'} size={15} />
        </button>

        <Dropdown
          align="right"
          trigger={
            <div className={styles.userTrigger}>
              <div className={styles.avatar}>{initials}</div>
              <span>{user?.username ?? user?.email ?? '用户'}</span>
              <Icon name="chevron" size={12} />
            </div>
          }
          items={[
            {
              label: '退出登录',
              icon: <Icon name="close" size={14} />,
              danger: true,
              onClick: () => void logout(),
            },
          ]}
        />
      </div>
    </div>
  );
}
