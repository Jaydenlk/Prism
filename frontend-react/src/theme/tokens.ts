export const palette = {
  paper: '#F5F1EA',
  bg: '#EDE6D6',
  ink: '#1C1B18',
  ink2: '#3A3832',
  ink3: '#6B675E',
  ink4: '#9C9890',
  line: 'rgba(28,27,24,0.10)',
  lineStrong: 'rgba(28,27,24,0.18)',
  amber: '#B8803A',
  amberSoft: '#F5EDDC',
  rust: '#9B4A35',
  rustSoft: '#F3E1DA',
  teal: '#4E7C6E',
  tealSoft: '#DAE9E4',
  plum: '#7A4E58',
  danger: '#9B4A35',
  panel: '#EEEAE0',
} as const;

export const typography = {
  serif: "'Source Serif 4', 'Noto Serif SC', Georgia, serif",
  mono: "'JetBrains Mono', 'Consolas', 'Courier New', monospace",
} as const;

export const shadows = {
  sm: '0 2px 8px rgba(28,27,24,0.10), 0 1px 2px rgba(28,27,24,0.07)',
  md: '0 4px 18px rgba(28,27,24,0.12), 0 2px 4px rgba(28,27,24,0.08)',
} as const;

export const layout = {
  sidebarWidth: 240,
  topbarHeight: 48,
  statusbarHeight: 32,
  bubbleRadius: '18px 18px 6px 18px',
  mobileBreakpoint: 640,
} as const;

export type PaletteKey = keyof typeof palette;
