"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";

import { AGENTS } from "@/components/team/agents";
import { type AgentEvent, type TeamPage, teamApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const CHIP = "inline-flex items-center gap-1 rounded-full bg-grey-soft px-2.5 py-0.5 text-xs text-ink-2 hover:bg-glass-strong";

/** The proof behind each action: our copy of the content, or the original link. */
function EvidenceChips({ event }: { event: AgentEvent }) {
  if (event.evidence.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-wrap gap-1.5">
      {event.evidence.map((ev, i) => (
        <li key={`${ev.label}-${i}`}>
          {ev.snapshotId && event.saveId ? (
            <Link href={`/saves/${event.saveId}#copy`} className={CHIP}>
              <FileText className="size-3" aria-hidden />
              {ev.label}
            </Link>
          ) : ev.url ? (
            <a href={ev.url} target="_blank" rel="noreferrer" className={CHIP}>
              <ExternalLink className="size-3" aria-hidden />
              {ev.label}
            </a>
          ) : (
            <span className={CHIP}>{ev.label}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function timeAgo(iso: string): string {
  const seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  if (Math.abs(seconds) < 60) return relative.format(seconds, "second");
  if (Math.abs(seconds) < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (Math.abs(seconds) < 86400) return relative.format(Math.round(seconds / 3600), "hour");
  return relative.format(Math.round(seconds / 86400), "day");
}

export function TeamFeed({ showDevTools }: { showDevTools: boolean }) {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["team"],
    queryFn: () => teamApi.list(),
  });

  const onEvent = useCallback(
    (event: AgentEvent) => {
      queryClient.setQueryData<TeamPage>(["team"], (page) => {
        if (!page) return { items: [event], nextCursor: null };
        if (page.items.some((e) => e.id === event.id)) return page;
        return { ...page, items: [event, ...page.items] };
      });
    },
    [queryClient],
  );
  const status = useEventStream(onEvent);

  const echo = useMutation({ mutationFn: () => teamApi.echo("The team is listening.") });

  return (
    <section>
      <header className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-[28px] font-extrabold tracking-[-0.03em]">The team</h1>
          <p className="text-sm text-ink-2">What each agent did, with the proof.</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            status === "live" ? "bg-green-soft text-green" : "bg-amber-soft text-amber"
          }`}
        >
          {status === "live" ? "Live" : status === "connecting" ? "Connecting" : "Reconnecting"}
        </span>
      </header>

      {showDevTools && (
        <button
          type="button"
          onClick={() => echo.mutate()}
          disabled={echo.isPending}
          className="glass mb-4 rounded-full px-4 py-2 text-sm font-semibold"
        >
          {echo.isPending ? "Sending…" : "Send a test event"}
        </button>
      )}

      {isPending && <p className="text-ink-2">Loading the feed…</p>}
      {isError && <p className="text-ink-2">{error.message}</p>}
      {data && data.items.length === 0 && (
        <div className="glass rounded-[var(--radius-card)] p-6 text-ink-2">
          Nothing yet. When you save something, you&apos;ll see each agent work on it here.
        </div>
      )}

      <ul className="space-y-3">
        {data?.items.map((event) => {
          const { label, Icon } = AGENTS[event.agent];
          return (
            <li key={event.id} className="glass flex gap-3 rounded-[var(--radius-card)] p-4">
              <Icon className="mt-0.5 size-[18px] shrink-0 text-ink-2" strokeWidth={1.8} aria-hidden />
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.07em] text-muted">
                  {label} · {timeAgo(event.createdAt)}
                </p>
                {event.saveId ? (
                  <Link href={`/saves/${event.saveId}`} className="mt-1 block hover:underline">
                    {event.summary}
                  </Link>
                ) : (
                  <p className="mt-1">{event.summary}</p>
                )}
                <EvidenceChips event={event} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
