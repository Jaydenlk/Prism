export function getSourceBadge(source: string): { variant: 'teal' | 'plum' | 'amber' | 'neutral'; label: string } {
  switch (source) {
    case 'local': return { variant: 'teal', label: '本地' };
    case 'github': return { variant: 'plum', label: 'GitHub' };
    case 'marketplace': return { variant: 'amber', label: '市场' };
    default: return { variant: 'neutral', label: source };
  }
}
