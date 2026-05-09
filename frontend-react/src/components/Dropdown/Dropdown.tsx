import { useRef, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';
import styles from './Dropdown.module.css';

interface DropdownItem {
  label: string;
  onClick: () => void;
  icon?: ReactNode;
  danger?: boolean;
}

interface DropdownProps {
  trigger: ReactNode;
  items: DropdownItem[];
  align?: 'left' | 'right';
}

export function Dropdown({ trigger, items, align = 'left' }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handleMouseDown(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    }

    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [open]);

  function handleItemClick(item: DropdownItem) {
    item.onClick();
    setOpen(false);
  }

  return (
    <div ref={rootRef} className={styles.root}>
      <div onClick={() => setOpen((prev) => !prev)} style={{ display: 'inline-block' }}>
        {trigger}
      </div>
      {open && (
        <div className={cn(styles.menu, align === 'right' ? styles.menuRight : styles.menuLeft)}>
          {items.map((item, i) => (
            <button
              key={i}
              className={cn(styles.item, item.danger ? styles.danger : undefined)}
              onClick={() => handleItemClick(item)}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
