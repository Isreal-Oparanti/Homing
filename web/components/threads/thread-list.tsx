"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Sparkles } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";

import { EmptyState } from "@/components/shell/empty-state";
import { type AgentEvent, threadsApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return ` · last saved ${d.getDate()} ${d.toLocaleString("en-GB", { month: "short" })} ${d.getFullYear()}`;
}

/** The goals your saves serve, fullest first. */
export function ThreadList() {
  const queryClient = useQueryClient();
  const [asked, setAsked] = useState(false);
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["threads"],
    queryFn: () => threadsApi.list(),
  });
  const organise = useMutation({
    mutationFn: () => threadsApi.rebuild(),
    onSuccess: () => setAsked(true),
  });

  // What's it for? says "Organised …" in The team when it's done: refresh then.
  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.agent === "for" && (event.action === "rebuilt" || event.action === "placed")) {
        if (event.action === "rebuilt") setAsked(false);
        void queryClient.invalidateQueries({ queryKey: ["threads"] });
      }
    },
    [queryClient],
  );
  useEventStream(onEvent);

  if (isPending) return <p className="text-ink-2">Looking at your goals…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;

  const button = (
    <div className="mt-4">
      <button
        type="button"
        onClick={() => organise.mutate()}
        disabled={organise.isPending || asked}
        className="glass flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold disabled:opacity-60"
      >
        <Sparkles className="size-4" aria-hidden />
        {asked ? "Organising your saves…" : "Organise my saves"}
      </button>
      {asked && (
        <p className="mt-1 text-sm text-muted">
          What&apos;s it for? is reading your whole pile. Watch it in{" "}
          <Link href="/agents" className="underline">
            Your agents
          </Link>
          ; this page updates when it&apos;s done.
        </p>
      )}
      {organise.isError && <p className="mt-1 text-sm text-red">{organise.error.message}</p>}
    </div>
  );

  if (data.items.length === 0) {
    return (
      <>
        <EmptyState
          title="No threads yet."
          body="As you save things, Homing groups them by the goal they serve."
        />
        {data.unplaced > 1 && button}
      </>
    );
  }
  return (
    <section>
      <ul className="grid gap-3 sm:grid-cols-2">
        {data.items.map((t) => (
          <li key={t.id}>
            <Link
              href={`/threads/${t.id}`}
              className="glass block h-full rounded-[var(--radius-card)] px-4 py-3 hover:bg-glass-strong"
            >
              <p className="flex items-center gap-1.5 font-semibold">
                <span className="truncate">{t.title}</span>
                {t.locked && <Lock className="size-3.5 shrink-0 text-muted" aria-label="Named by you" />}
              </p>
              {t.summary && <p className="mt-0.5 line-clamp-2 text-sm text-ink-2">{t.summary}</p>}
              <p className="mt-1 text-xs text-muted">
                {t.saves} {t.saves === 1 ? "save" : "saves"}
                {when(t.lastSavedAt)}
              </p>
            </Link>
          </li>
        ))}
      </ul>
      {data.unplaced > 0 && (
        <p className="mt-3 text-sm text-ink-2">
          {data.unplaced} {data.unplaced === 1 ? "save isn't" : "saves aren't"} in a goal yet.
        </p>
      )}
      {button}
    </section>
  );
}
