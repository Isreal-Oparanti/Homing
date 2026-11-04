"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

import { ByLine } from "@/components/team/by-line";
import { findsApi, type AgentEvent, type DismissWhy, type Find } from "@/lib/api";
import { useEventStream } from "@/lib/events";

const WHY_NOT: [DismissWhy, string][] = [
  ["wrong_country", "Wrong country"],
  ["not_my_stage", "Not my stage"],
  ["already_applied", "Already applied"],
  ["not_interested", "Not interested"],
];

function FindRow({ find }: { find: Find }) {
  const queryClient = useQueryClient();
  const done = () => void queryClient.invalidateQueries({ queryKey: ["finds"] });
  const keep = useMutation({ mutationFn: () => findsApi.keep(find.id), onSuccess: done });
  const dismiss = useMutation({
    mutationFn: (why?: DismissWhy) => findsApi.dismiss(find.id, why),
    onSuccess: done,
  });
  const [asking, setAsking] = useState(false);
  const busy = keep.isPending || dismiss.isPending;
  const said = find.quotes.find((q) => q.label === "What the page says");
  return (
    <li className="py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.07em] text-muted">
        {find.goal ? `For ${find.goal}` : "Found for you"}
        {find.closes && <span className="text-amber"> · {find.closes}</span>}
      </p>
      <p className="font-display mt-1 text-lg font-bold leading-snug tracking-[-0.02em]">{find.name}</p>
      <p className="mt-1 text-[15px]">{find.what}</p>
      {said && (
        <p className="mt-1 text-sm text-ink-2">
          On the page: <q>{said.quote}</q>
        </p>
      )}
      <p
        className={`mt-1.5 flex items-center gap-1.5 text-sm font-semibold ${
          find.verdict === "fits_you" ? "text-green" : find.verdict === "needs_your_answer" ? "text-amber" : "text-ink-2"
        }`}
      >
        <BadgeCheck className="size-4" aria-hidden />
        {find.fit}
      </p>
      <details className="mt-1.5 text-sm text-ink-2">
        <summary className="cursor-pointer">How Homing checked it</summary>
        <ul className="mt-1.5 space-y-1">
          {find.quotes.filter((q) => q !== said).map((q) => (
            <li key={q.label}>
              {q.label}: <q>{q.quote}</q>
            </li>
          ))}
          {find.rules.map((r) => (
            <li key={r.quote}>
              {r.result === "meets" ? "You meet this" : "Still to answer"}: {r.plain} (<q>{r.quote}</q>)
            </li>
          ))}
        </ul>
        <ByLine models={["muse-wonder-1.0"]} how="searched and chose the page; code checked every quote on it" />
      </details>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => keep.mutate()}
          disabled={busy}
          className="rounded-full bg-red px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          Keep
        </button>
        <a
          href={find.url}
          target="_blank"
          rel="noopener noreferrer"
          className="glass inline-flex items-center gap-1 rounded-full px-4 py-1.5 text-sm font-semibold"
        >
          {find.site} <ExternalLink className="size-3.5" aria-hidden />
        </a>
        <button
          type="button"
          onClick={() => setAsking(true)}
          disabled={busy}
          aria-expanded={asking}
          className="rounded-full px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
        >
          Not for me
        </button>
      </div>
      {asking && (
        <div className="mt-2">
          <p className="text-sm text-ink-2">Why not? Homing rules out the like next time.</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {WHY_NOT.map(([why, label]) => (
              <button
                key={why}
                type="button"
                onClick={() => dismiss.mutate(why)}
                disabled={busy}
                className="glass rounded-full px-3 py-1 text-sm font-semibold"
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => dismiss.mutate(undefined)}
              disabled={busy}
              className="rounded-full px-3 py-1 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
            >
              Skip
            </button>
          </div>
        </div>
      )}
      {(keep.isError || dismiss.isError) && (
        <p className="mt-1 text-sm text-red">{(keep.error ?? dismiss.error)?.message}</p>
      )}
    </li>
  );
}

/** What What's it for? found on the web for the person's goals: only what passed code's checks.
 * On a goal's page, `threadId` narrows it to that goal and adds Find more. */
export function FoundForYou({ threadId }: { threadId?: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["finds", threadId ?? "all"],
    queryFn: () => findsApi.list(threadId),
  });
  // Asked of the server, so "Looking now" is still there after leaving the page and coming back.
  const status = useQuery({
    queryKey: ["finding", threadId],
    queryFn: () => findsApi.looking(threadId ?? ""),
    enabled: Boolean(threadId),
  });
  const looking = status.data ?? false;
  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.agent !== "for" || (threadId && event.threadId !== threadId)) return;
      if (event.action === "found") void queryClient.invalidateQueries({ queryKey: ["finds"] });
      if (event.action === "find_done" || event.action === "find_started") {
        void queryClient.invalidateQueries({ queryKey: ["finding", threadId] });
      }
    },
    [queryClient, threadId],
  );
  useEventStream(onEvent);
  const findNow = useMutation({
    mutationFn: () => findsApi.findNow(threadId ?? ""),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["finding", threadId] }),
  });
  const finds = data ?? [];
  if (!threadId && finds.length === 0) {
    return (
      <p className="mt-5 px-1 text-sm text-muted">
        Every morning, What&apos;s it for? looks on the web for more for your goals, and keeps only what
        it checked on the organisation&apos;s own page. Open a goal in{" "}
        <Link href="/threads" className="font-semibold underline">
          Threads
        </Link>{" "}
        to look now.
      </p>
    );
  }
  return (
    <section className="mt-5">
      <h2 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.07em] text-muted">
        Found for you
      </h2>
      <div className="glass rounded-[var(--radius-card)] px-5">
        {finds.length > 0 && (
          <ul className="divide-y divide-line">
            {finds.map((f) => (
              <FindRow key={f.id} find={f} />
            ))}
          </ul>
        )}
        {threadId && (
          <div className={`py-4 ${finds.length ? "border-t border-line" : ""}`}>
            {looking ? (
              <p className="text-sm text-ink-2">
                Looking on the web now. Watch each step in{" "}
                <Link href="/agents" className="font-semibold underline">
                  Your agents
                </Link>
                …
              </p>
            ) : (
              <>
                <p className="text-sm text-ink-2">
                  What&apos;s it for? looks on the web for more like what you saved here, and keeps
                  only what it checked on the organisation&apos;s own page.
                </p>
                <button
                  type="button"
                  onClick={() => findNow.mutate()}
                  disabled={findNow.isPending}
                  className="glass mt-2 inline-flex items-center gap-1.5 rounded-full px-4 py-1.5 text-sm font-semibold"
                >
                  <Search className="size-3.5" aria-hidden />
                  Find more
                </button>
                {findNow.isError && <p className="mt-1 text-sm text-red">{findNow.error.message}</p>}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
