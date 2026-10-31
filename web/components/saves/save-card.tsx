"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, ExternalLink, Lock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";

import { QuestionView } from "@/components/saves/question";
import { AGENTS } from "@/components/team/agents";
import {
  type AgentEvent,
  type Answer,
  type CheckedItem,
  type Copy,
  type ForAnswer,
  type SaveCard,
  type TrueAnswer,
  type WhenAnswer,
  savesApi,
} from "@/lib/api";
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
  official_text: "Official page",
  ocr_text: "Words on it",
  pdf_text: "The PDF's text",
};

const FINDING_KIND: Record<string, string> = {
  left_out: "Left out of the post",
  differs: "Differs from the post",
  confirmed: "Confirmed",
  closed: "Closed",
};

function ordinal(n: number) {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th";
  return `${n}${suffix}`;
}

const WORKING: Record<Exclude<Answer, "what">, string> = {
  true: "Checking the official page…",
  for: "Finding what it's for…",
  when: "Working out when you'll need it…",
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

function Muted({ children }: { children: React.ReactNode }) {
  return <p className="text-muted">{children}</p>;
}

/** Only findings code verified against the official page get here (docs/05). */
const VERDICT: Record<string, { label: string; tone: string }> = {
  fits_you: { label: "Fits you", tone: "bg-green-soft text-green" },
  not_for_you: { label: "Not for you", tone: "bg-grey-soft text-ink-2" },
  needs_your_answer: { label: "Needs your answer", tone: "bg-amber-soft text-amber" },
  closed: { label: "Closed", tone: "bg-grey-soft text-ink-2" },
  couldnt_confirm: { label: "Couldn't confirm", tone: "bg-grey-soft text-ink-2" },
};

const FIRST_QUESTIONS = 3; // more than this on one card is too much at once

const RESULT: Record<string, { mark: string; tone: string; words: string }> = {
  meets: { mark: "✓", tone: "text-green", words: "You meet this" },
  fails: { mark: "✗", tone: "text-red", words: "You don't meet this" },
  unknown: { mark: "?", tone: "text-amber", words: "Not known yet" },
};

/** The flyer, screenshots or PDF itself, so you can see what you saved. */
function Files({ saveId, kind, count }: { saveId: string; kind: string; count: number }) {
  const src = (i: number) => `/api/backend/saves/${saveId}/files/${i}`;
  if (kind === "pdf") {
    return (
      <a href={src(0)} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm text-ink-2 underline">
        <ExternalLink className="size-3.5" aria-hidden />
        Open the PDF
      </a>
    );
  }
  return (
    <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
      {Array.from({ length: count }, (_, i) => (
        <a key={i} href={src(i)} target="_blank" rel="noreferrer" className="shrink-0">
          {/* eslint-disable-next-line @next/next/no-img-element -- private, owner-only file */}
          <img src={src(i)} alt={`Saved image ${i + 1}`} className="h-36 w-auto rounded-xl border border-line object-cover" />
        </a>
      ))}
    </div>
  );
}

const ITEM_VERDICT: Record<string, string> = {
  fits_you: "Fits you",
  not_for_you: "Not for you",
  needs_your_answer: "Needs your answer",
  closed: "Closed",
  couldnt_confirm: "Couldn't confirm",
  checked: "Checked",
};

/** A save that lists several opportunities: each one checked on its own page, side by side. */
function ItemsView({ items }: { items: CheckedItem[] }) {
  const done = items.filter((i) => i.status === "done");
  const counts = new Map<string, number>();
  for (const i of done) counts.set(i.verdict ?? "couldnt_confirm", (counts.get(i.verdict ?? "couldnt_confirm") ?? 0) + 1);
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
        {items.length} items, each checked on its own page
      </p>
      <p className="mt-0.5 text-sm text-ink-2">
        {[...counts.entries()].map(([v, n]) => `${n} ${(ITEM_VERDICT[v] ?? v).toLowerCase()}`).join(" · ")}
        {done.length < items.length && `${done.length ? " · " : ""}${items.length - done.length} still checking`}
      </p>
      <ul className="mt-2 divide-y divide-line">
        {items.map((item, i) => {
          const verdict = item.verdict ? VERDICT[item.verdict] : null;
          const failing = item.rules.filter((r) => r.strength === "required" && r.result === "fails");
          const reason =
            item.status !== "done"
              ? null
              : item.note ??
                (failing.length ? `You don't meet: ${failing.map((r) => r.plain).join("; ")}` : null) ??
                item.findings[0]?.point ??
                null;
          return (
            <li key={i} className="py-2">
              <div className="flex items-center gap-2">
                <p className="min-w-0 flex-1 truncate font-semibold">
                  {item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {item.name}
                    </a>
                  ) : (
                    item.name
                  )}
                </p>
                {item.status !== "done" ? (
                  <Working text="Checking…" />
                ) : (
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${verdict?.tone ?? "bg-grey-soft text-ink-2"}`}>
                    {ITEM_VERDICT[item.verdict ?? ""] ?? "Checked"}
                  </span>
                )}
              </div>
              {reason && <p className="mt-0.5 text-sm text-ink-2">{reason}</p>}
              {item.deadline && <p className="text-xs text-muted">Closes {item.deadline.display}</p>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** Only findings and rules code verified against the official page get here (docs/05). */
function TrueAnswerView({
  saveId,
  answer,
  postHasDeadline,
}: {
  saveId: string;
  answer: TrueAnswer;
  postHasDeadline: boolean;
}) {
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const reply = useMutation({
    // Wait for the card's own refresh, so the message and the verdict change together.
    mutationFn: async ({ id, value }: { id: string; value: string | number | boolean }) => {
      const text = await savesApi.answer(saveId, id, value);
      await queryClient.refetchQueries({ queryKey: ["save", saveId] });
      return text;
    },
    onSuccess: (text) => {
      setSummary(text);
      for (const key of [["save"], ["today"], ["saves"], ["profile"]]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });

  if (answer.verdict === "nothing_to_check") return <Muted>Nothing to check.</Muted>;
  // Questions Homing remembers for every opportunity (age, languages, country) come first;
  // the ones only this opportunity needs come after.
  const questions = [
    ...answer.questions.filter((q) => !q.id.startsWith("rule:")),
    ...answer.questions.filter((q) => q.id.startsWith("rule:")),
  ];
  const host = answer.officialUrl ? hostOf(answer.officialUrl) : null;
  const verdict = VERDICT[answer.verdict];
  const failing = answer.rules.filter((r) => r.strength === "required" && r.result === "fails");

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {verdict && (
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${verdict.tone}`}>{verdict.label}</span>
        )}
        {host && !answer.note && (
          <span className="text-sm text-ink-2">
            Checked against{" "}
            <a href={answer.officialUrl!} target="_blank" rel="noreferrer" className="underline">
              {host}
            </a>
          </span>
        )}
      </div>
      {answer.verdict === "closed" && (
        <p className="font-semibold">
          {answer.fromPost || !answer.officialUrl ? "Closed, going by the date in the post." : "Closed, per the official page."}
        </p>
      )}
      {answer.verdict === "not_for_you" && failing.length > 0 && (
        <p>
          You don&apos;t meet: {failing.map((r) => r.plain).join("; ")}.{" "}
          <Link href="/profile" className="text-sm text-ink-2 underline">
            Change your answers
          </Link>
        </p>
      )}
      {answer.verdict === "fits_you" && <p>Nothing on the official page rules you out.</p>}
      {answer.fromPost &&
        answer.verdict === "couldnt_confirm" &&
        answer.rules.length > 0 &&
        answer.rules.every((r) => r.strength !== "required" || r.result === "meets") && (
          <p>Going by the post, nothing rules you out.</p>
        )}
      {answer.note && <p className="text-amber">{answer.note}</p>}

      {questions.length > 0 && (
        <div className="space-y-3 rounded-xl bg-amber-soft/60 p-3">
          <p className="text-sm text-ink-2">
            Answer {questions.length === 1 ? "this" : "these"} to see if it fits you.
            {questions.some((q) => !q.id.startsWith("rule:")) &&
              " Homing remembers, so other opportunities won't ask again."}
          </p>
          {questions.slice(0, showAll ? undefined : FIRST_QUESTIONS).map((q) => (
            <QuestionView
              key={q.id}
              question={q}
              busy={reply.isPending}
              onAnswer={(value) => reply.mutate({ id: q.id, value })}
            />
          ))}
          {!showAll && questions.length > FIRST_QUESTIONS && (
            <button type="button" onClick={() => setShowAll(true)} className="text-sm text-ink-2 underline">
              Show {questions.length - FIRST_QUESTIONS} more{" "}
              {questions.length - FIRST_QUESTIONS === 1 ? "question" : "questions"}
            </button>
          )}
        </div>
      )}
      {summary && <p className="text-sm font-semibold text-green">{summary}</p>}
      {reply.isError && <p className="text-sm text-amber">{reply.error.message}</p>}

      {answer.rules.length > 0 && (
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Who can apply</p>
          <ul className="mt-1 space-y-2">
            {answer.rules.map((r, i) => {
              const result = RESULT[r.result] ?? RESULT.unknown;
              return (
                <li key={i} className="grid grid-cols-[18px_1fr] gap-1.5">
                  <span className={`font-bold ${result.tone}`} title={result.words} aria-label={result.words}>
                    {result.mark}
                  </span>
                  <div>
                    <p>
                      {r.plain.replace(/\s*\(preferred\)\s*$/i, "")}
                      {r.strength === "preferred" && <span className="text-muted"> · preferred, not required</span>}
                    </p>
                    <p className="text-xs text-ink-2">
                      “{r.quote}”
                      {host && <span className="text-green"> · on {host}</span>}
                      {answer.fromPost && <span className="text-muted"> · in the post, not confirmed</span>}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {answer.items.length > 0 && <ItemsView items={answer.items} />}

      {answer.findings.length > 0 && (
        <ul className="space-y-2.5">
          {answer.findings.map((f, i) => (
            <li key={i}>
              <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                {answer.samePage && f.kind === "left_out" ? "On the official page" : (FINDING_KIND[f.kind] ?? f.kind)}
              </p>
              <p>{f.point}</p>
              <blockquote className="mt-1 border-l-2 border-green pl-2.5 text-sm text-ink-2">
                “{f.quote}”
                {host && <span className="mt-0.5 block text-xs text-green">Found word for word on {host}</span>}
              </blockquote>
            </li>
          ))}
        </ul>
      )}
      {answer.deadline ? (
        <p className="text-sm">
          Official closing date: {answer.deadline.display}
          {!answer.deadline.tzStated && <span className="text-muted"> · time zone not stated</span>}
        </p>
      ) : host && postHasDeadline && !answer.note ? (
        <p className="text-sm text-ink-2">We didn&apos;t find a closing date on the official page.</p>
      ) : null}
    </div>
  );
}

function ForAnswerView({ answer }: { answer: ForAnswer }) {
  const thread = answer.threads[0];
  return (
    <div className="space-y-1">
      {answer.duplicateOf && (
        <p>
          You saved this before.{" "}
          <Link href={`/saves/${answer.duplicateOf}`} className="underline">
            See the first one
          </Link>
          .
        </p>
      )}
      {thread ? (
        <p>
          <span className="font-semibold">{thread.title}</span>
          {thread.count > 1 ? `: your ${ordinal(thread.position)} save on this.` : ": the first save on this."}
        </p>
      ) : (
        !answer.duplicateOf && <Muted>Not sure what this is for yet.</Muted>
      )}
    </div>
  );
}

function WhenAnswerView({ answer }: { answer: WhenAnswer }) {
  if (answer.kind !== "date") return <Muted>{answer.explanation}</Muted>;
  return (
    <div>
      <p>{answer.explanation}</p>
      {(!answer.tzStated || answer.sourceText) && (
        <p className="mt-0.5 text-xs text-muted">
          {answer.sourceText && <>From “{answer.sourceText}”</>}
          {answer.sourceText && !answer.tzStated && " · "}
          {!answer.tzStated && "time zone not stated"}
        </p>
      )}
    </div>
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
      {save.files > 0 && !isPrivate && <Files saveId={save.id} kind={save.kind} count={save.files} />}

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
              <Muted>Not used for private saves.</Muted>
            ) : pending.includes("what") ? (
              <Muted>Waiting for the reading.</Muted>
            ) : pending.includes(answer) ? (
              <Working text={WORKING[answer]} />
            ) : answer === "true" && card.true ? (
              <TrueAnswerView
                saveId={save.id}
                answer={card.true}
                postHasDeadline={(what?.keyFacts.dates ?? []).some((d) => d.role === "deadline")}
              />
            ) : answer === "for" && card.for ? (
              <ForAnswerView answer={card.for} />
            ) : answer === "when" && card.when ? (
              <WhenAnswerView answer={card.when} />
            ) : (
              <Muted>{NOT_YET[answer]}</Muted>
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
      q.state.data && q.state.data.pending.length > 0 && !q.state.data.save.error ? 3000 : false,
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
