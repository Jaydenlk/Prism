export interface TimeGroups<T> {
  today: T[];
  yesterday: T[];
  thisWeek: T[];
  earlier: T[];
}

export function groupByTime<T extends { updated_at: string }>(items: T[]): TimeGroups<T> {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  const startOfWeek = new Date(startOfToday.getTime() - (now.getDay() || 7) * 86400000);

  const groups: TimeGroups<T> = { today: [], yesterday: [], thisWeek: [], earlier: [] };
  const sorted = [...items].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime());

  for (const s of sorted) {
    const d = new Date(s.updated_at);
    if (d >= startOfToday) groups.today.push(s);
    else if (d >= startOfYesterday) groups.yesterday.push(s);
    else if (d >= startOfWeek) groups.thisWeek.push(s);
    else groups.earlier.push(s);
  }
  return groups;
}

export function formatTime(isoStr: string | null): string {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  if (d >= startOfToday) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  if (d >= startOfYesterday) return '昨天';
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}
