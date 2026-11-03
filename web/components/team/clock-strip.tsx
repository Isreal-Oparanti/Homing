import { AgentMark } from "@/components/team/agent-mark";
import { AGENTS, FOUR } from "@/components/team/agents";
import type { TeamOverview } from "@/lib/api";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

function strength(n: number): number {
  if (n === 0) return 0;
  if (n === 1) return 0.35;
  if (n < 6) return 0.6;
  return 1;
}

/** Today, hour by hour, in the person's own time: one row per agent, one cell per hour. */
export function ClockStrip({ overview }: { overview: TeamOverview }) {
  const total = FOUR.reduce(
    (n, a) => n + (overview.hours[a] ?? []).reduce((x, y) => x + y, 0),
    0,
  );
  return (
    <section className="glass rounded-[var(--radius-card)] p-4 sm:p-5">
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-lg font-bold tracking-[-0.02em]">
          Today, hour by hour
        </h2>
        <p className="text-sm text-ink-2">
          {total === 0
            ? "Quiet so far today"
            : `${total} ${total === 1 ? "step" : "steps"} so far`}
        </p>
      </header>
      <div className="grid grid-cols-[minmax(0,5.5rem)_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5">
        {FOUR.map((a) => (
          <div key={a} className="contents">
            <p className="flex items-center gap-1.5 truncate text-xs font-semibold text-ink-2">
              <AgentMark agent={a} size={16} />
              {AGENTS[a].short}
            </p>
            <div className="grid grid-cols-24 gap-[3px]">
              {HOURS.map((h) => {
                const n = overview.hours[a]?.[h] ?? 0;
                const now = h === overview.hourNow;
                return (
                  <span
                    key={h}
                    title={`${String(h).padStart(2, "0")}:00 · ${n} ${n === 1 ? "step" : "steps"}`}
                    className={`h-4 rounded-[4px] ${now ? "ring-1 ring-ink/40" : ""} ${h > overview.hourNow ? "opacity-40" : ""}`}
                    style={{
                      background: n ? AGENTS[a].color : "var(--grey-soft)",
                      opacity: n ? strength(n) : undefined,
                    }}
                  />
                );
              })}
            </div>
          </div>
        ))}
        <span />
        <div className="grid grid-cols-24 text-[11px] text-muted">
          {HOURS.map((h) => (
            <span key={h} className={h % 6 === 0 ? "" : "invisible"}>
              {String(h).padStart(2, "0")}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
