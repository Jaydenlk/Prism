import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Icon } from '@/components/Icon/Icon';
import type { IconName } from '@/components/Icon/Icon';
import styles from './AdminLayout.module.css';

interface NavItem {
  path: string;
  icon: IconName;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/admin', icon: 'layers', label: '概览' },
  { path: '/admin/users', icon: 'admin', label: '用户' },
  { path: '/admin/audit', icon: 'book', label: '审计日志' },
  { path: '/admin/providers', icon: 'globe', label: '供应商' },
  { path: '/admin/invites', icon: 'link', label: '邀请码' },
];

function isActive(current: string, itemPath: string): boolean {
  if (itemPath === '/admin') return current === '/admin';
  return current.startsWith(itemPath);
}

export function AdminLayout() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div className={styles.shell}>
      {/* Dark sidebar rail — desktop */}
      <aside className={styles.rail}>
        <div className={styles.railTitle}>管理员</div>
        {NAV_ITEMS.map(item => (
          <button
            key={item.path}
            className={`${styles.navItem} ${isActive(location.pathname, item.path) ? styles.navItemActive : ''}`}
            onClick={() => navigate(item.path)}
          >
            <Icon name={item.icon} size={14} />
            {item.label}
          </button>
        ))}
      </aside>

      {/* Mobile horizontal tab bar */}
      <div className={styles.tabBar}>
        {NAV_ITEMS.map(item => (
          <button
            key={item.path}
            className={`${styles.tabBarItem} ${isActive(location.pathname, item.path) ? styles.tabBarItemActive : ''}`}
            onClick={() => navigate(item.path)}
          >
            <Icon name={item.icon} size={13} />
            {item.label}
          </button>
        ))}
      </div>

      <div className={styles.content}>
        <Outlet />
      </div>
    </div>
  );
}
