"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Lock } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback } from "react";

import { AGENTS } from "@/components/team/agents";
import { type AgentEvent, type Answer, type SaveCard, savesApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

const PLATFORM: Record<string, string> = {
  youtube: "YouTube",
  x: "X",
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  web: "Web page",
};

const NOT_YET: Record<Exclude<Answer, "what">, string> = {
  true: "Not checked yet.",
  for: "Not placed in a thread yet.",
  when: "No date yet.",
};

function savedOn(iso: string) {
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" }).format(
    new Date(iso),
  );
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function AnswerRow({ answer, children }: { answer: Answer; children: React.ReactNode }) {
  const { label, Icon } = AGENTS[answer];
  return (
    <div className="grid grid-cols-[22px_1fr] gap-2.5 border-t border-line py-3">
      <Icon className="mt-0.5 size-[18px] text-ink-2" strokeWidth={1.8} aria-hidden />
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-muted">{label}</p>
        <div className="mt-0.5 text-[15px] leading-relaxed">{children}</div>
      </div>
    </div>
  );
}

function Working({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 text-ink-2">
      <span className="inline-block size-2 animate-pulse rounded-full bg-red" aria-hidden />
      {text}
    </p>
  );
}

function Card({ card }: { card: SaveCard }) {
  const { save, what, pending } = card;
  const isPrivate = save.visibility === "private";
  const title = isPrivate
    ? "Private save"
    : (what?.title ?? save.label ?? (save.url ? hostOf(save.url) : save.text?.slice(0, 80)) ?? "Your save");
  // Amounts and requirements only mean something on an opportunity; on a talk they're stray numbers.
  const facts = [
    ...(what?.keyFacts.dates ?? []).map((d) => d.text),
    ...(what?.isOpportunity ? (what.keyFacts.amounts ?? []).map((a) => a.text) : []),
    ...(what?.isOpportunity ? (what.keyFacts.requirements ?? []).map((r) => r.text) : []),
  ].slice(0, 6);

  return (
    <article className="glass rounded-[var(--radius-card)] p-5">
      <p className="text-xs text-muted">
        Saved {savedOn(save.savedAt)}
        {save.platform && ` · ${PLATFORM[save.platform] ?? save.platform}`}
        {isPrivate && " · Private"}
      </p>
      <h1 className="font-display mt-1 text-[22px] font-bold leading-snug tracking-[-0.02em]">{title}</h1>
      {save.url && (
        <a
          href={save.url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-flex max-w-full items-center gap-1 truncate text-sm text-ink-2 underline decoration-line underline-offset-2"
        >
          <ExternalLink className="size-3.5 shrink-0" aria-hidden />
          <span className="truncate">{save.url}</span>
        </a>
      )}

      <div className="mt-4">
        <AnswerRow answer="what">
          {isPrivate ? (
            <p className="flex items-start gap-2 text-ink-2">
              <Lock className="mt-1 size-4 shrink-0" aria-hidden />
              {what?.what ?? "Kept private. We never send these to AI."}
            </p>
          ) : what ? (
            <>
              <p>{what.what}</p>
              {facts.length > 0 && (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {facts.map((f) => (
                    <li key={f} className="rounded-full bg-grey-soft px-2.5 py-0.5 text-xs text-ink-2">
                      {f}
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : save.status === "failed" ? (
            <p className="text-amber">{save.error ?? "Couldn't read this save."}</p>
          ) : (
            <Working text="Reading it…" />
          )}
        </AnswerRow>
        {(["true", "for", "when"] as const).map((answer) => (
          <AnswerRow key={answer} answer={answer}>
            {isPrivate ? (
              <p className="text-muted">Not used for private saves.</p>
            ) : pending.includes("what") ? (
              <p className="text-muted">Waiting for the reading.</p>
            ) : (
              <p className="text-muted">{NOT_YET[answer]}</p>
            )}
          </AnswerRow>
        ))}
      </div>
    </article>
  );
}

export function SaveCardView() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["save", id],
    queryFn: () => savesApi.get(id),
    // Safety net for the live feed: keep asking while the reading is on its way.
    refetchInterval: (q) => (q.state.data?.pending.includes("what") ? 3000 : false),
  });

  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.saveId === id) void queryClient.invalidateQueries({ queryKey: ["save", id] });
    },
    [id, queryClient],
  );
  useEventStream(onEvent);

  if (isPending) return <p className="text-ink-2">Opening your save…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  return <Card card={data} />;
}
