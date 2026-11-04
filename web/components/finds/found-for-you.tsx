"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

import { ByLine } from "@/components/team/by-line";
import { findsApi, type AgentEvent, type Find } from "@/lib/api";
import { useEventStream } from "@/lib/events";

function FindRow({ find }: { find: Find }) {
  const queryClient = useQueryClient();
  const done = () => void queryClient.invalidateQueries({ queryKey: ["finds"] });
  const keep = useMutation({ mutationFn: () => findsApi.keep(find.id), onSuccess: done });
  const dismiss = useMutation({ mutationFn: () => findsApi.dismiss(find.id), onSuccess: done });
  const busy = keep.isPending || dismiss.isPending;
  return (
    <li className="py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.07em] text-muted">
        {find.goal ? `For ${find.goal}` : "Found for you"}
        {find.closes && <span className="text-amber"> · {find.closes}</span>}
      </p>
      <p className="font-display mt-1 text-lg font-bold leading-snug tracking-[-0.02em]">{find.name}</p>
      <p className="mt-1 text-[15px]">{find.what}</p>
      <p className="mt-1.5 flex items-center gap-1.5 text-sm font-semibold text-green">
        <BadgeCheck className="size-4" aria-hidden />
        {find.fit}
      </p>
      <details className="mt-1.5 text-sm text-ink-2">
        <summary className="cursor-pointer">How Homing checked it</summary>
        <ul className="mt-1.5 space-y-1">
          {find.quotes.map((q) => (
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
          onClick={() => dismiss.mutate()}
          disabled={busy}
          className="rounded-full px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
        >
          Not for me
        </button>
      </div>
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
  const [looking, setLooking] = useState(false);
  const { data } = useQuery({
    queryKey: ["finds", threadId ?? "all"],
    queryFn: () => findsApi.list(threadId),
  });
  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.agent !== "for" || (threadId && event.threadId !== threadId)) return;
      if (event.action === "found") void queryClient.invalidateQueries({ queryKey: ["finds"] });
      if (event.action === "find_done") setLooking(false);
    },
    [queryClient, threadId],
  );
  useEventStream(onEvent);
  const findNow = useMutation({
    mutationFn: () => findsApi.findNow(threadId ?? ""),
    onSuccess: () => setLooking(true),
  });
  const finds = data ?? [];
  if (!threadId && finds.length === 0) return null;
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
