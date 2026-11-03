import { Sparkles } from "lucide-react";

import { modelName } from "@/components/team/by-line";
import type { ModelUse } from "@/lib/api";

const NUMBER = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** Which Meta models did the work, from the record of real calls. */
export function ModelStrip({ models }: { models: ModelUse[] }) {
  if (models.length === 0) return null;
  const merged = new Map<string, ModelUse>();
  for (const m of models) {
    const name = modelName(m.model);
    const seen = merged.get(name);
    merged.set(
      name,
      seen
        ? {
            model: name,
            callsToday: seen.callsToday + m.callsToday,
            calls: seen.calls + m.calls,
            tokens: seen.tokens + m.tokens,
          }
        : { ...m, model: name },
    );
  }
  return (
    <section className="glass rounded-[var(--radius-card)] p-4 sm:p-5">
      <h2 className="font-display text-lg font-bold tracking-[-0.02em]">Meta models at work</h2>
      <p className="mt-0.5 text-sm text-ink-2">
        Every step below names the model that did it. Steps without one were done by code.
      </p>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {[...merged.values()].map((m) => (
          <li key={m.model} className="flex items-start gap-2.5 rounded-2xl bg-grey-soft/70 px-3 py-2.5">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-ink-2" aria-hidden />
            <div className="min-w-0">
              <p className="font-semibold">{m.model}</p>
              <p className="text-xs text-ink-2">
                {m.calls.toLocaleString()} {m.calls === 1 ? "call" : "calls"}
                {m.tokens > 0 && ` · ${NUMBER.format(m.tokens)} tokens`}
                {m.callsToday > 0 && ` · ${m.callsToday} today`}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
