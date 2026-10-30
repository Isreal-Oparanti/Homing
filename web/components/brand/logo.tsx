type IconProps = { size?: number; className?: string };

/** The Homing icon: a lowercase "h" whose right leg lands on a dot (home). */
export function HomingIcon({ size = 28, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" className={className} aria-hidden>
      <rect width="64" height="64" rx="18" fill="var(--red)" />
      <path
        d="M23 14v36M23 37c0-9 18-9 18 0v4"
        fill="none"
        stroke="#fff"
        strokeWidth="7"
        strokeLinecap="round"
      />
      <circle cx="41" cy="50" r="4.5" fill="#fff" />
    </svg>
  );
}

/** The wordmark: "homing" with a red dot on the i. */
export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-display font-extrabold tracking-[-0.045em] ${className}`}>
      hom
      <span className="relative">
        ı
        <span
          className="absolute left-1/2 top-[0.06em] size-[0.22em] -translate-x-1/2 rounded-full bg-red"
          aria-hidden
        />
      </span>
      ng
    </span>
  );
}

export function Logo({ size = 26 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2 text-xl text-ink" aria-label="Homing">
      <HomingIcon size={size} />
      <Wordmark />
    </span>
  );
}
