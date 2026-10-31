"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";

import { EmptyState } from "@/components/shell/empty-state";
import { type AgentEvent, todayApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

/** Up to three saves that need you now, each with why now and the next step. */
export function TodayList() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["today"],
    queryFn: () => todayApi.get(),
  });

  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.agent === "when" || event.agent === "true") {
        void queryClient.invalidateQueries({ queryKey: ["today"] });
      }
    },
    [queryClient],
  );
  useEventStream(onEvent);

  if (isPending) return <p className="text-ink-2">Looking at what&apos;s coming up…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  if (data.cards.length === 0) {
    return (
      <EmptyState
        title="Nothing needs you yet."
        body="When something you saved matters, it comes back here with the next step."
      />
    );
  }
  return (
    <ul className="space-y-3">
      {data.cards.map((card) => (
        <li key={card.saveId}>
          <Link
            href={`/saves/${card.saveId}`}
            className="glass block rounded-[var(--radius-card)] p-5 hover:bg-glass-strong"
          >
            <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.07em] text-amber">
              <CalendarClock className="size-3.5" aria-hidden />
              {card.whyNow}
            </p>
            <p className="font-display mt-1 text-lg font-bold leading-snug tracking-[-0.02em]">
              {card.title}
            </p>
            <p className="mt-1 text-[15px]">{card.nextStep}</p>
            {(card.unconfirmed || !card.tzStated) && (
              <p className="mt-1 text-xs text-muted">
                {card.unconfirmed && "The date is from the post, not the official page"}
                {card.unconfirmed && !card.tzStated && " · "}
                {!card.tzStated && "time zone not stated"}
              </p>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}
