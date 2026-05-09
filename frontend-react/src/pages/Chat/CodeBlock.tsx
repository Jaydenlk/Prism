import { useEffect, useRef, useState } from 'react';
import Prism from 'prismjs';
import { Icon } from '@/components/Icon/Icon';
import styles from './CodeBlock.module.css';

interface CodeBlockProps {
  code: string;
  language?: string;
}

export function CodeBlock({ code, language }: CodeBlockProps) {
  const codeRef = useRef<HTMLElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!codeRef.current) return;
    Prism.highlightElement(codeRef.current);
  }, [code, language]);

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch(() => {});
  }

  const langClass = language ? `language-${language}` : '';

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.lang}>{language ?? 'text'}</span>
        <button className={styles.copyBtn} onClick={handleCopy} title="复制代码">
          <Icon name={copied ? 'check' : 'copy'} size={14} />
        </button>
      </div>
      <div className={styles.codeArea}>
        <code ref={codeRef} className={langClass}>
          {code}
        </code>
      </div>
    </div>
  );
}
