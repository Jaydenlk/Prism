import { useState, useCallback } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import styles from './AppLayout.module.css';

const PAGE_TITLES: Record<string, string> = {
  '/': '对话',
  '/sessions': '会话',
  '/settings': '设置',
  '/usage': '用量',
  '/skills': '技能市场',
  '/plugins': '插件构建',
  '/admin': '管理',
  '/observability': '可观测性',
};

export function AppLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const handleNavigate = useCallback((page: string) => {
    navigate(page);
    setSidebarOpen(false);
  }, [navigate]);

  const title = PAGE_TITLES[location.pathname] ?? 'Prism';

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>跳至主内容</a>
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        currentPage={location.pathname}
        onNavigate={handleNavigate}
      />
      <div className={styles.main}>
        <Topbar title={title} onMenuClick={() => setSidebarOpen(!sidebarOpen)} />
        <div id="main" className={styles.content}>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
