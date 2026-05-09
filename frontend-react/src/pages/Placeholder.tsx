interface PlaceholderProps {
  name: string;
}

export function Placeholder({ name }: PlaceholderProps) {
  return (
    <div style={{ padding: 40 }}>
      <h2 style={{ fontFamily: 'var(--serif)', marginBottom: 8 }}>{name}</h2>
      <p style={{ color: 'var(--ink-3)' }}>Phase 3+ で実装予定</p>
    </div>
  );
}
