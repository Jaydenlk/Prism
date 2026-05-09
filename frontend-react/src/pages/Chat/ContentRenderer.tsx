import { useEffect, useRef, useMemo } from 'react';
import Prism from 'prismjs';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-python';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-bash';
import 'prismjs/components/prism-markdown';
import 'prismjs/themes/prism-tomorrow.css';
import { renderMarkdown } from '@/utils/markdown';
import styles from './ContentRenderer.module.css';

interface ContentRendererProps {
  content: string;
  className?: string;
}

export function ContentRenderer({ content, className }: ContentRendererProps) {
  const ref = useRef<HTMLDivElement>(null);

  const html = useMemo(() => renderMarkdown(content), [content]);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.querySelectorAll<HTMLElement>('pre code').forEach(el => {
      Prism.highlightElement(el);
    });
  }, [content]);

  return (
    <div
      ref={ref}
      className={`${styles.prose}${className ? ` ${className}` : ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
