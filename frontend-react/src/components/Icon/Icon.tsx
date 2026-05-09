import type { CSSProperties, JSX } from 'react';

export type IconName =
  | 'search' | 'plus' | 'chat' | 'sessions' | 'settings' | 'usage'
  | 'skills' | 'plugin' | 'admin' | 'chevron' | 'close' | 'check'
  | 'attach' | 'shield' | 'alert' | 'info' | 'clock' | 'book'
  | 'terminal' | 'folder' | 'pin' | 'globe' | 'copy' | 'fork'
  | 'refresh' | 'arrowUp' | 'arrowRight' | 'more' | 'layers' | 'send'
  | 'eye' | 'download' | 'upload' | 'filter' | 'flask' | 'flow'
  | 'link' | 'menu' | 'sparkle';

const paths: Record<IconName, JSX.Element> = {
  search:     <><circle cx="7" cy="7" r="5"/><path d="M11 11l4 4"/></>,
  plus:       <><path d="M8 3v10M3 8h10"/></>,
  chat:       <><path d="M2 4h12v8H6l-3 2V4z"/></>,
  sessions:   <><path d="M3 4h10M3 8h10M3 12h6"/></>,
  settings:   <><circle cx="8" cy="8" r="2"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4"/></>,
  usage:      <><path d="M2 13h12M4 10v3M7 7v6M10 9v4M13 4v9"/></>,
  skills:     <><path d="M8 1l6 3-6 3-6-3 6-3zM2 8l6 3 6-3M2 11l6 3 6-3"/></>,
  plugin:     <><path d="M5 2v3M11 2v3M3 5h10v4a4 4 0 01-4 4H7a4 4 0 01-4-4V5zM8 13v2"/></>,
  admin:      <><path d="M8 1l6 2v4c0 4-2.5 7-6 8-3.5-1-6-4-6-8V3l6-2z"/></>,
  chevron:    <><path d="M6 3l5 5-5 5"/></>,
  close:      <><path d="M3 3l10 10M13 3L3 13"/></>,
  check:      <><path d="M3 8l3 3 7-7"/></>,
  attach:     <><path d="M12 7l-5 5a3 3 0 01-4-4l6-6a2 2 0 013 3l-6 6a1 1 0 01-1-1l5-5"/></>,
  shield:     <><path d="M8 1l5 2v4c0 3-2 6-5 7-3-1-5-4-5-7V3l5-2zM6 8l1.5 1.5L10 7"/></>,
  alert:      <><path d="M8 2l7 12H1L8 2zM8 6v4M8 12v0.5"/></>,
  info:       <><circle cx="8" cy="8" r="6"/><path d="M8 7v4M8 5v0.5"/></>,
  clock:      <><circle cx="8" cy="8" r="6"/><path d="M8 5v3l2 1"/></>,
  book:       <><path d="M3 2h10v12H5a2 2 0 01-2-2V2zM3 12a2 2 0 012-2h8"/></>,
  terminal:   <><rect x="2" y="3" width="12" height="10" rx="2"/><path d="M5 6l2 2-2 2M9 10h3"/></>,
  folder:     <><path d="M2 4h4l1 2h7v7H2V4z"/></>,
  pin:        <><path d="M8 2l3 3-1 1v3l2 2H2l2-2V6l-1-1 3-3h2z"/></>,
  globe:      <><circle cx="8" cy="8" r="6"/><path d="M2 8h12M8 2c2 2 2 10 0 12M8 2c-2 2-2 10 0 12"/></>,
  copy:       <><rect x="5" y="5" width="9" height="9" rx="2"/><path d="M2 11V3a2 2 0 012-2h7"/></>,
  fork:       <><circle cx="4" cy="3" r="2"/><circle cx="12" cy="3" r="2"/><circle cx="8" cy="13" r="2"/><path d="M4 5v3a2 2 0 002 2h4a2 2 0 002-2V5"/></>,
  refresh:    <><path d="M2 8a6 6 0 0110-4.5L13 5M14 8a6 6 0 01-10 4.5L3 11M13 2v3h-3M3 14v-3h3"/></>,
  arrowUp:    <><path d="M8 13V3M3 8l5-5 5 5"/></>,
  arrowRight: <><path d="M3 8h10M9 4l4 4-4 4"/></>,
  more:       <><circle cx="4" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="12" cy="8" r="1.2"/></>,
  layers:     <><path d="M8 2l6 3-6 3-6-3 6-3zM2 8l6 3 6-3M2 11l6 3 6-3"/></>,
  send:       <><path d="M2 8l12-5-5 12-2-5-5-2z"/></>,
  eye:        <><path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/></>,
  download:   <><path d="M8 2v8M4 7l4 4 4-4M2 14h12"/></>,
  upload:     <><path d="M8 14V6M4 9l4-4 4 4M2 2h12"/></>,
  filter:     <><path d="M2 3h12l-4.5 6v4.5L6.5 12V9L2 3z"/></>,
  flask:      <><path d="M6 2h4M7 2v4l-4 7a1 1 0 001 1.5h8A1 1 0 0013 13L9 6V2"/></>,
  flow:       <><rect x="2" y="2" width="5" height="4" rx="1.5"/><rect x="9" y="10" width="5" height="4" rx="1.5"/><path d="M4 6v4M4 10h9"/></>,
  link:       <><path d="M9 7a3 3 0 00-4 0L3 9a3 3 0 004 4l1-1M7 9a3 3 0 004 0l2-2a3 3 0 00-4-4L8 4"/></>,
  menu:       <><path d="M2 4h12M2 8h12M2 12h12"/></>,
  sparkle:    <><path d="M8 2v4M8 10v4M2 8h4M10 8h4M4 4l2 2M10 10l2 2M4 12l2-2M10 6l2-2"/></>,
};

interface IconProps {
  name: IconName;
  size?: number;
  stroke?: number;
  className?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 16, stroke = 1.5, className, style }: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
    >
      {paths[name]}
    </svg>
  );
}

interface PrismMarkProps {
  size?: number;
}

export function PrismMark({ size = 22 }: PrismMarkProps) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" style={{ display: 'block' }}>
      <path d="M4 20 L12 5 L20 20 Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill="none"/>
      <line x1="1" y1="14" x2="7" y2="14" stroke="currentColor" strokeWidth="0.8"/>
      <line x1="17" y1="13" x2="23" y2="11" stroke="#9B4A35" strokeWidth="0.9"/>
      <line x1="17" y1="14" x2="23" y2="13.5" stroke="#B8803A" strokeWidth="0.9"/>
      <line x1="17" y1="15" x2="23" y2="15" stroke="#6B7A4A" strokeWidth="0.9"/>
      <line x1="17" y1="16" x2="23" y2="16.5" stroke="#4E7C6E" strokeWidth="0.9"/>
      <line x1="17" y1="17" x2="23" y2="19" stroke="#7A4E58" strokeWidth="0.9"/>
    </svg>
  );
}

interface PrismGlyphProps {
  size?: number;
}

export function PrismGlyph({ size = 140 }: PrismGlyphProps) {
  return (
    <svg viewBox="0 0 180 160" width={size} height={size} fill="none">
      <line x1="10" y1="90" x2="70" y2="90" stroke="currentColor" strokeWidth="0.8" opacity="0.5"/>
      <path d="M70 90 L100 35 L130 90 Z" stroke="currentColor" strokeWidth="1.1" fill="none" strokeLinejoin="round"/>
      <g opacity="0.9">
        <line x1="130" y1="90" x2="172" y2="66" stroke="#9B4A35" strokeWidth="0.9"/>
        <line x1="130" y1="90" x2="174" y2="78" stroke="#B8803A" strokeWidth="0.9"/>
        <line x1="130" y1="90" x2="174" y2="90" stroke="#6B7A4A" strokeWidth="0.9"/>
        <line x1="130" y1="90" x2="174" y2="102" stroke="#4E7C6E" strokeWidth="0.9"/>
        <line x1="130" y1="90" x2="172" y2="114" stroke="#7A4E58" strokeWidth="0.9"/>
      </g>
      <circle cx="10" cy="90" r="2" fill="currentColor"/>
    </svg>
  );
}
