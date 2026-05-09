import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { IconName } from '../Icon/Icon';
import { Icon } from '../Icon/Icon';
import { Spinner } from '../Spinner/Spinner';
import { cn } from '../../utils/cn';
import styles from './Button.module.css';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  icon?: IconName;
  loading?: boolean;
  children?: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  icon,
  loading = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={loading || disabled}
      className={cn(styles.button, styles[variant], styles[size], className)}
    >
      {loading ? (
        <Spinner size={size === 'sm' ? 13 : 15} />
      ) : icon ? (
        <Icon name={icon} size={size === 'sm' ? 13 : 15} />
      ) : null}
      {children}
    </button>
  );
}
