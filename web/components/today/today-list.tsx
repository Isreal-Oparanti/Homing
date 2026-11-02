"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CalendarPlus, Clock, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { EmptyState } from "@/components/shell/empty-state";
import { type AgentEvent, type Moment, type TodayCard, todayApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

/** "Something coming up?": the person's own moments, and the goals each one needs. */
function Moments({ moments }: { moments: Moment[] }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const add = useMutation({
    mutationFn: () => todayApi.addMoment(text.trim()),
    onSuccess: () => {
      setText("");
      void queryClient.invalidateQueries({ queryKey: ["today"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => todayApi.removeMoment(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["today"] }),
  });

  return (
    <section className="glass mb-5 rounded-[var(--radius-card)] p-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim().length >= 3) add.mutate();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Something coming up? e.g. recording my demo on Tuesday evening"
          aria-label="Something coming up"
          className="min-w-0 flex-1 bg-transparent px-1 outline-none placeholder:text-muted"
        />
        <button
          type="submit"
          disabled={text.trim().length < 3 || add.isPending}
          className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {add.isPending ? "Adding…" : "Add"}
        </button>
      </form>
      {add.isError && <p className="mt-1 text-sm text-red">{add.error.message}</p>}
      {moments.length > 0 && (
        <ul className="mt-3 space-y-2">
          {moments.map((m) => (
            <li key={m.id} className="flex items-start gap-2 text-sm">
              <Clock className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <p>
                  <span className="font-semibold">{m.text}</span>
                  <span className="text-ink-2"> · {m.display}</span>
                </p>
                <p className="text-ink-2">
                  {m.threads.length > 0 ? (
                    <>
                      Goes with{" "}
                      {m.threads.map((t, i) => (
                        <span key={t.id}>
                          {i > 0 && ", "}
                          <Link href={`/threads/${t.id}`} className="font-semibold hover:underline">
                            {t.title}
                          </Link>
                        </span>
                      ))}
                    </>
                  ) : (
                    "Looking for the goals it needs…"
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => remove.mutate(m.id)}
                aria-label={`Remove ${m.text}`}
                className="rounded-full p-1 text-muted hover:bg-grey-soft"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Card({ card }: { card: TodayCard }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const act = useMutation({
    mutationFn: (action: "use" | "dismiss" | "later") => todayApi.act(card.id, action),
    onSuccess: (_, action) => {
      void queryClient.invalidateQueries({ queryKey: ["today"] });
      if (action === "use") {
        router.push(card.saveId ? `/saves/${card.saveId}` : `/threads/${card.threadIds[0] ?? ""}`);
      }
    },
  });
  const prep = card.kind === "prep";
  return (
    <li className="glass rounded-[var(--radius-card)] p-5">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.07em] text-amber">
        {prep ? <Sparkles className="size-3.5" aria-hidden /> : <CalendarClock className="size-3.5" aria-hidden />}
        {card.whyNow}
      </p>
      <p className="font-display mt-1 text-lg font-bold leading-snug tracking-[-0.02em]">{card.title}</p>
      <p className="mt-1 text-[15px]">{card.nextStep}</p>
      {!prep && (card.unconfirmed || !card.tzStated) && (
        <p className="mt-1 text-xs text-muted">
          {card.unconfirmed && "The date is from the post, not the official page"}
          {card.unconfirmed && !card.tzStated && " · "}
          {!card.tzStated && "time zone not stated"}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => act.mutate("use")}
          disabled={act.isPending}
          className="rounded-full bg-red px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          Open
        </button>
        <button
          type="button"
          onClick={() => act.mutate("later")}
          disabled={act.isPending}
          className="glass rounded-full px-4 py-1.5 text-sm font-semibold"
        >
          Later
        </button>
        <button
          type="button"
          onClick={() => act.mutate("dismiss")}
          disabled={act.isPending}
          className="rounded-full px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
        >
          Dismiss
        </button>
        {card.saveId && card.dueAt && (
          <a
            href={`/api/backend/saves/${card.saveId}/calendar.ics`}
            className="ml-auto flex items-center gap-1 text-sm font-semibold text-ink-2 hover:underline"
          >
            <CalendarPlus className="size-4" aria-hidden />
            Add to calendar
          </a>
        )}
      </div>
      {act.isError && <p className="mt-1 text-sm text-red">{act.error.message}</p>}
    </li>
  );
}

/** At most three things that need you now, chosen by When will you need it?. */
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
  return (
    <>
      <Moments moments={data.moments} />
      {data.cards.length === 0 ? (
        <EmptyState
          title="Nothing needs you yet."
          body="When something you saved matters, it comes back here with the next step. Tell Homing what's coming up, and it gets your saves ready."
        />
      ) : (
        <ul className="space-y-3">
          {data.cards.map((card) => (
            <Card key={card.id} card={card} />
          ))}
        </ul>
      )}
    </>
  );
}
