/** While a screen loads: the shape of what's coming, with the words for screen readers. */
export function Loading({
  label,
  lines = 4,
}: {
  label: string;
  lines?: number;
}) {
  return (
    <div
      className="glass rounded-[var(--radius-card)] p-5"
      role="status"
      aria-live="polite"
    >
      <div className="h-3 w-24 animate-pulse rounded-full bg-grey-soft" />
      <div className="mt-3 h-6 w-3/4 animate-pulse rounded-full bg-grey-soft" />
      <div className="mt-5 space-y-2.5">
        {Array.from({ length: lines }, (_, i) => (
          <div
            key={i}
            className="h-3.5 animate-pulse rounded-full bg-grey-soft"
            style={{ width: `${92 - ((i * 17) % 35)}%` }}
          />
        ))}
      </div>
      <p className="mt-4 text-sm text-muted">{label}</p>
    </div>
  );
}
