"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText } from "lucide-react";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import { AgentMap } from "@/components/team/agent-map";
import { AgentMark } from "@/components/team/agent-mark";
import { AGENTS, FOUR } from "@/components/team/agents";
import { ClockStrip } from "@/components/team/clock-strip";
import {
  type Agent,
  type AgentEvent,
  type TeamOverview,
  type TeamPage,
  teamApi,
} from "@/lib/api";
import { useEventStream } from "@/lib/events";

const CHIP =
  "inline-flex items-center gap-1 rounded-full bg-grey-soft px-2.5 py-0.5 text-xs text-ink-2 hover:bg-glass-strong";

/** The proof behind each action: our copy of the content, or the original link. */
function EvidenceChips({ event }: { event: AgentEvent }) {
  if (event.evidence.length === 0) return null;
  return (
    <ul className="mt-1.5 flex flex-wrap gap-1.5">
      {event.evidence.map((ev, i) => (
        <li key={`${ev.label}-${i}`}>
          {ev.snapshotId && event.saveId ? (
            <Link href={`/saves/${event.saveId}#copy`} className={CHIP}>
              <FileText className="size-3" aria-hidden />
              {ev.label}
            </Link>
          ) : ev.url?.startsWith("/") ? (
            <Link href={ev.url} className={CHIP}>
              {ev.label}
            </Link>
          ) : ev.url ? (
            <a
              href={ev.url}
              target="_blank"
              rel="noreferrer"
              className={CHIP}
              title={ev.quote}
            >
              <ExternalLink className="size-3" aria-hidden />
              {ev.label}
            </a>
          ) : (
            <span className={CHIP}>
              {ev.quote ? `${ev.label}: “${ev.quote}”` : ev.label}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

const CLOCK = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
});
const DAY = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
});

function stamp(iso: string): string {
  const at = new Date(iso);
  const today = new Date().toDateString() === at.toDateString();
  return today ? CLOCK.format(at) : DAY.format(at);
}

/** Your agents: the live map, today's clock, and every step they took, with the proof. */
export function TeamFeed({ showDevTools }: { showDevTools: boolean }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<Agent | null>(null);
  const [incoming, setIncoming] = useState<AgentEvent | null>(null);
  const settle = useRef<ReturnType<typeof setTimeout>>(undefined);
  const feed = useQuery({ queryKey: ["team"], queryFn: () => teamApi.list() });
  const overview = useQuery({
    queryKey: ["team-overview"],
    queryFn: () => teamApi.overview(),
  });

  const onEvent = useCallback(
    (event: AgentEvent) => {
      queryClient.setQueryData<TeamPage>(["team"], (page) => {
        if (!page) return { items: [event], nextCursor: null };
        if (page.items.some((e) => e.id === event.id)) return page;
        return { ...page, items: [event, ...page.items] };
      });
      // Today's clock counts the step in the hour it happened.
      queryClient.setQueryData<TeamOverview>(["team-overview"], (o) => {
        if (!o || !(event.agent in o.hours)) return o;
        const row = [...o.hours[event.agent]];
        row[o.hourNow] += 1;
        return { ...o, hours: { ...o.hours, [event.agent]: row } };
      });
      setIncoming(event);
      // New saves and goals: refresh the map's counts once things settle.
      clearTimeout(settle.current);
      settle.current = setTimeout(
        () =>
          void queryClient.invalidateQueries({ queryKey: ["team-overview"] }),
        5000,
      );
    },
    [queryClient],
  );
  const status = useEventStream(onEvent);
  const echo = useMutation({
    mutationFn: () => teamApi.echo("Your agents are listening."),
  });

  const items = (feed.data?.items ?? []).filter(
    (e) => !selected || e.agent === selected,
  );

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-[28px] font-extrabold tracking-[-0.03em]">
            Your agents
          </h1>
          <p className="text-sm text-ink-2">
            Four agents work on your saves. Every step, with the proof.
          </p>
        </div>
        <span
          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
            status === "live"
              ? "bg-green-soft text-green"
              : "bg-amber-soft text-amber"
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${status === "live" ? "bg-green" : "bg-amber"}`}
          />
          {status === "live"
            ? "Live"
            : status === "connecting"
              ? "Connecting"
              : "Reconnecting"}
        </span>
      </header>

      {showDevTools && (
        <button
          type="button"
          onClick={() => echo.mutate()}
          disabled={echo.isPending}
          className="glass rounded-full px-4 py-2 text-sm font-semibold"
        >
          {echo.isPending ? "Sending…" : "Send a test event"}
        </button>
      )}

      {overview.data && (
        <>
          <AgentMap
            overview={overview.data}
            incoming={incoming}
            selected={selected}
            onSelect={setSelected}
          />
          <ClockStrip overview={overview.data} />
        </>
      )}

      <section className="glass rounded-[var(--radius-card)] p-4 sm:p-5">
        <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-display text-lg font-bold tracking-[-0.02em]">
            Every step
          </h2>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setSelected(null)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                selected === null
                  ? "bg-ink text-white"
                  : "bg-grey-soft text-ink-2"
              }`}
            >
              All
            </button>
            {FOUR.map((a) => (
              <button
                key={a}
                type="button"
                onClick={() => setSelected(selected === a ? null : a)}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${
                  selected === a
                    ? "bg-ink text-white"
                    : "bg-grey-soft text-ink-2"
                }`}
              >
                <AgentMark agent={a} size={14} />
                {AGENTS[a].label}
              </button>
            ))}
          </div>
        </header>

        {feed.isPending && (
          <p className="py-3 text-ink-2">Loading every step…</p>
        )}
        {feed.isError && (
          <p className="py-3 text-ink-2">{feed.error.message}</p>
        )}
        {feed.data && items.length === 0 && (
          <p className="py-3 text-ink-2">
            {selected
              ? `${AGENTS[selected].label} hasn't done anything yet.`
              : "Nothing yet. When you save something, you'll see each agent work on it here."}
          </p>
        )}

        <ol className="divide-y divide-line">
          {items.map((event) => (
            <li
              key={event.id}
              className="grid grid-cols-[3.25rem_1.25rem_minmax(0,1fr)] gap-x-2.5 py-3"
            >
              <time
                dateTime={event.createdAt}
                className="pt-0.5 font-mono text-xs tabular-nums text-muted"
              >
                {stamp(event.createdAt)}
              </time>
              <span className="pt-0.5">
                <AgentMark agent={event.agent} size={18} />
              </span>
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-muted">
                  {AGENTS[event.agent].label}
                </p>
                {event.saveId ? (
                  <Link
                    href={`/saves/${event.saveId}`}
                    className="mt-0.5 block hover:underline"
                  >
                    {event.summary}
                  </Link>
                ) : (
                  <p className="mt-0.5">{event.summary}</p>
                )}
                <EvidenceChips event={event} />
              </div>
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}
