import { Component, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error): void {
    import('@/api/client').then(({ reportError }) => {
      reportError({
        message: error.message,
        stack: error.stack || '',
        name: error.name,
        url: window.location.href,
        severity: 'error',
        context: {},
      });
    });
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100%', padding: 40, textAlign: 'center',
        }}>
          <h2 style={{ fontFamily: 'var(--serif)', marginBottom: 8 }}>出了点问题</h2>
          <p style={{ color: 'var(--ink-3)', marginBottom: 16 }}>
            {this.state.error?.message || '页面加载失败'}
          </p>
          <button
            onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
            style={{
              padding: '8px 16px', borderRadius: 10, border: '1px solid var(--line)',
              background: 'var(--paper)', cursor: 'pointer', fontFamily: 'var(--serif)',
            }}
          >
            重新加载
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
