import { useState } from 'react';
import { ProfileTab } from './ProfileTab';
import { ProvidersTab } from './ProvidersTab';
import { McpTab } from './McpTab';
import { ImTab } from './ImTab';
import { PreferencesTab } from './PreferencesTab';
import styles from './SettingsPage.module.css';

type TabId = 'profile' | 'providers' | 'mcp' | 'im' | 'preferences';

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'profile', label: '个人资料' },
  { id: 'providers', label: '模型供应商' },
  { id: 'mcp', label: 'MCP 服务' },
  { id: 'im', label: '即时通讯' },
  { id: 'preferences', label: '偏好设置' },
];

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('profile');

  return (
    <div className={styles.page}>
      <div className={styles.tabBar}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className={styles.content}>
        {activeTab === 'profile' && <ProfileTab />}
        {activeTab === 'providers' && <ProvidersTab />}
        {activeTab === 'mcp' && <McpTab />}
        {activeTab === 'im' && <ImTab />}
        {activeTab === 'preferences' && <PreferencesTab />}
      </div>
    </div>
  );
}
