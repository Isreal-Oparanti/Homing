export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="glass rounded-[var(--radius-card)] p-6">
      <p className="font-display text-lg font-bold tracking-[-0.02em]">{title}</p>
      <p className="mt-1 text-ink-2">{body}</p>
    </div>
  );
}

export function PageTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="mb-5">
      <h1 className="font-display text-[28px] font-extrabold tracking-[-0.03em]">{title}</h1>
      <p className="text-sm text-ink-2">{subtitle}</p>
    </header>
  );
}
