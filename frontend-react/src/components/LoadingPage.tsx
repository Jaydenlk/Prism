import { Spinner } from '@/components/Spinner/Spinner';

export function LoadingPage() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', padding: 40 }}>
      <Spinner size={32} />
    </div>
  );
}
