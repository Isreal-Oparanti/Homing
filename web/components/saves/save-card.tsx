"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, ExternalLink, Lock } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";

import { AGENTS } from "@/components/team/agents";
import { type AgentEvent, type Answer, type Copy, type SaveCard, savesApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

const PLATFORM: Record<string, string> = {
  youtube: "YouTube",
  x: "X",
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  web: "Web page",
};

const COPY_KIND: Record<string, string> = {
  page_text: "Page text",
  post_text: "Post text",
  transcript: "Captions",
  metadata: "Title and description",
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
      <div className="min-w-0">
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

/** The owner's private text stays hidden until they ask, and is never kept in the query cache. */
function PrivateText({ saveId }: { saveId: string }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function show() {
    setLoading(true);
    setError(null);
    try {
      setText(await savesApi.reveal(saveId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't show it. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-2">
      {text === null ? (
        <div className="flex items-center gap-3 rounded-xl bg-grey-soft px-3 py-2.5">
          <span className="select-none font-mono text-sm tracking-widest text-muted blur-[3px]" aria-hidden>
            ••••-••••-••••
          </span>
          <button
            type="button"
            onClick={show}
            disabled={loading}
            className="ml-auto flex items-center gap-1.5 rounded-full bg-ink px-3 py-1 text-xs font-semibold text-white disabled:opacity-60"
          >
            <Eye className="size-3.5" aria-hidden />
            {loading ? "Showing…" : "Show"}
          </button>
        </div>
      ) : (
        <div className="flex items-start gap-3 rounded-xl bg-grey-soft px-3 py-2.5">
          <p className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-sm">{text}</p>
          <button
            type="button"
            onClick={() => setText(null)}
            className="flex items-center gap-1.5 rounded-full bg-white/80 px-3 py-1 text-xs font-semibold"
          >
            <EyeOff className="size-3.5" aria-hidden />
            Hide
          </button>
        </div>
      )}
      {error && <p className="mt-1 text-sm text-amber">{error}</p>}
    </div>
  );
}

/** Our copy of the content: the proof behind "What is it?", kept even if the link dies. */
function Copies({ copies }: { copies: Copy[] }) {
  // Opened from a Team proof chip (/saves/{id}#copy). Only ever rendered in the browser.
  const [open, setOpen] = useState(() => window.location.hash === "#copy");
  if (copies.length === 0) return null;
  return (
    <details
      id="copy"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="mt-2 border-t border-line pt-3"
    >
      <summary className="cursor-pointer text-sm font-semibold text-ink-2">
        Our copy of the content
      </summary>
      <div className="mt-2 space-y-3">
        {copies.map((copy) => (
          <section key={copy.id}>
            <p className="text-xs text-muted">
              {COPY_KIND[copy.kind] ?? copy.kind} · {copy.chars.toLocaleString("en-GB")} characters
              {copy.sourceUrl && (
                <>
                  {" · "}
                  <a href={copy.sourceUrl} target="_blank" rel="noreferrer" className="underline">
                    {hostOf(copy.sourceUrl)}
                  </a>
                </>
              )}
            </p>
            <p className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-xl bg-grey-soft p-3 text-sm text-ink-2">
              {copy.excerpt}
              {copy.chars > copy.excerpt.length && "…"}
            </p>
          </section>
        ))}
      </div>
    </details>
  );
}

function Card({ card }: { card: SaveCard }) {
  const { save, what, copies, pending } = card;
  const isPrivate = save.visibility === "private";
  const paused = !what && save.status !== "failed" && save.error;
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
      {save.url && !isPrivate && (
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
            <>
              <p className="flex items-start gap-2 text-ink-2">
                <Lock className="mt-1 size-4 shrink-0" aria-hidden />
                {what?.what ?? "Kept private. We never send these to AI."}
              </p>
              <PrivateText saveId={save.id} />
            </>
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
          ) : paused ? (
            <p className="text-amber">{save.error}</p>
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
        <Copies copies={copies} />
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
    // Safety net for the live feed: keep asking while the reading is on its way, but not
    // while it's paused (a budget pause lasts until tomorrow).
    refetchInterval: (q) =>
      q.state.data?.pending.includes("what") && !q.state.data.save.error ? 3000 : false,
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
