"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, ExternalLink, Lock } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";

import { QuestionView } from "@/components/saves/question";
import { AgentMark } from "@/components/team/agent-mark";
import { ByLine } from "@/components/team/by-line";
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
import { Loading } from "@/components/shell/loading";

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
  pasted_text: "What you pasted",
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
  const suffix =
    tens >= 11 && tens <= 13
      ? "th"
      : (({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ??
        "th");
  return `${n}${suffix}`;
}

const WORKING: Record<Exclude<Answer, "what">, string> = {
  true: "Checking the source…",
  for: "Finding what it's for…",
  when: "Working out when you'll need it…",
};

const NOT_YET: Record<Exclude<Answer, "what">, string> = {
  true: "Not checked yet.",
  for: "Not placed in a thread yet.",
  when: "No date yet.",
};

function savedOn(iso: string) {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  }).format(new Date(iso));
}

function hostOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function AnswerRow({
  answer,
  by,
  children,
}: {
  answer: Answer;
  /** What produced this answer: Meta models by name, or code. */
  by?: { models: string[]; how: string };
  children: React.ReactNode;
}) {
  const { label } = AGENTS[answer];
  return (
    <div className="grid grid-cols-[22px_1fr] gap-2.5 border-t border-line py-3">
      <span className="mt-0.5">
        <AgentMark agent={answer} size={18} />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-muted">
          {label}
        </p>
        <div className="mt-0.5 text-[15px] leading-relaxed">{children}</div>
        {by && <ByLine models={by.models} how={by.how} />}
      </div>
    </div>
  );
}

function Working({ text }: { text: string }) {
  return (
    <p className="flex items-center gap-2 text-ink-2">
      <span
        className="inline-block size-2 animate-pulse rounded-full bg-red"
        aria-hidden
      />
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
  needs_your_answer: {
    label: "Needs your answer",
    tone: "bg-amber-soft text-amber",
  },
  closed: { label: "Closed", tone: "bg-grey-soft text-ink-2" },
  couldnt_confirm: {
    label: "Couldn't confirm",
    tone: "bg-grey-soft text-ink-2",
  },
};

const FIRST_QUESTIONS = 3; // more than this on one card is too much at once

const RESULT: Record<string, { mark: string; tone: string; words: string }> = {
  meets: { mark: "✓", tone: "text-green", words: "You meet this" },
  fails: { mark: "✗", tone: "text-red", words: "You don't meet this" },
  unknown: { mark: "?", tone: "text-amber", words: "Not known yet" },
};

const FIRST_FINDINGS = 3;

/** "7 rules · 1 met · 6 to check": the whole list in one line. */
function ruleSummary(rules: { result: string }[]): string {
  const count = (r: string) => rules.filter((x) => x.result === r).length;
  const parts = [`${rules.length} ${rules.length === 1 ? "rule" : "rules"}`];
  if (count("meets")) parts.push(`${count("meets")} met`);
  if (count("fails")) parts.push(`${count("fails")} not met`);
  if (count("unknown")) parts.push(`${count("unknown")} to check`);
  return parts.join(" · ");
}

/** The flyer, screenshots or PDF itself, so you can see what you saved. */
function Files({
  saveId,
  kind,
  count,
}: {
  saveId: string;
  kind: string;
  count: number;
}) {
  const src = (i: number) => `/api/backend/saves/${saveId}/files/${i}`;
  if (kind === "pdf") {
    return (
      <a
        href={src(0)}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-sm text-ink-2 underline"
      >
        <ExternalLink className="size-3.5" aria-hidden />
        Open the PDF
      </a>
    );
  }
  return (
    <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
      {Array.from({ length: count }, (_, i) => (
        <a
          key={i}
          href={src(i)}
          target="_blank"
          rel="noreferrer"
          className="shrink-0"
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- private, owner-only file */}
          <img
            src={src(i)}
            alt={`Saved image ${i + 1}`}
            className="h-36 w-auto rounded-xl border border-line object-cover"
          />
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

/** Rules only the person can judge, with no per-item question: listed for them to check. */
function checkYourself(item: CheckedItem): string[] {
  return item.rules
    .filter(
      (r) =>
        r.rule === "other" &&
        r.strength === "required" &&
        r.result === "unknown",
    )
    .map((r) => r.plain);
}

/** A save that lists several opportunities: each one checked on its own page, side by side. */
function ItemsView({ items }: { items: CheckedItem[] }) {
  const done = items.filter((i) => i.status === "done");
  const counts = new Map<string, number>();
  for (const i of done)
    counts.set(
      i.verdict ?? "couldnt_confirm",
      (counts.get(i.verdict ?? "couldnt_confirm") ?? 0) + 1,
    );
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
        {items.length} items, each checked on its own page
      </p>
      <p className="mt-0.5 text-sm text-ink-2">
        {[...counts.entries()]
          .map(([v, n]) => `${n} ${(ITEM_VERDICT[v] ?? v).toLowerCase()}`)
          .join(" · ")}
        {done.length < items.length &&
          `${done.length ? " · " : ""}${items.length - done.length} still checking`}
      </p>
      <ul className="mt-2 divide-y divide-line">
        {items.map((item, i) => {
          const verdict = item.verdict ? VERDICT[item.verdict] : null;
          const failing = item.rules.filter(
            (r) => r.strength === "required" && r.result === "fails",
          );
          // A difference first, then something left out, then a confirmation.
          const telling = ["differs", "left_out", "confirmed"]
            .map((kind) => item.findings.find((f) => f.kind === kind))
            .find(Boolean);
          const reason =
            item.status !== "done"
              ? null
              : (item.problem ??
                (failing.length
                  ? `You don't meet: ${failing.map((r) => r.plain).join("; ")}`
                  : null) ??
                (telling
                  ? `${telling.kind === "differs" ? "Differs: " : ""}${telling.point}`
                  : null));
          return (
            <li key={i} className="py-2">
              <div className="flex items-center gap-2">
                <p className="min-w-0 flex-1 truncate font-semibold">
                  {item.url ? (
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                    >
                      {item.name}
                    </a>
                  ) : (
                    item.name
                  )}
                </p>
                {item.status !== "done" ? (
                  <Working text="Checking…" />
                ) : (
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${verdict?.tone ?? "bg-grey-soft text-ink-2"}`}
                  >
                    {ITEM_VERDICT[item.verdict ?? ""] ?? "Checked"}
                  </span>
                )}
              </div>
              {item.note && (
                <p className="mt-0.5 text-xs text-muted">
                  The post says: {item.note}
                </p>
              )}
              {reason && <p className="mt-0.5 text-sm text-ink-2">{reason}</p>}
              {item.status === "done" && checkYourself(item).length > 0 && (
                <p className="mt-0.5 text-sm text-ink-2">
                  Check yourself: {checkYourself(item).join("; ")}
                </p>
              )}
              {item.officialUrl && (
                <p className="text-xs text-muted">
                  Checked on{" "}
                  <a
                    href={item.officialUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    {hostOf(item.officialUrl)}
                  </a>
                  {item.foundBy === "search" && " · found by searching"}
                </p>
              )}
              {item.deadline && (
                <p className="text-xs text-muted">
                  Closes {item.deadline.display}
                </p>
              )}
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
  const [showFindings, setShowFindings] = useState(false);
  const reply = useMutation({
    // Wait for the card's own refresh, so the message and the verdict change together.
    mutationFn: async ({
      id,
      value,
    }: {
      id: string;
      value: string | number | boolean;
    }) => {
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
  const checkNow = useMutation({
    mutationFn: () => savesApi.checkNow(saveId),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["save", saveId] }),
  });

  if (answer.verdict === "nothing_to_check")
    return <Muted>Nothing to check.</Muted>;
  if (answer.verdict === "not_checked") {
    return (
      <div>
        <p className="text-sm text-ink-2">
          Not checked yet. It came in with your WhatsApp import and looks closed
          or old, so Homing held off to save effort.
        </p>
        <button
          type="button"
          onClick={() => checkNow.mutate()}
          disabled={checkNow.isPending || checkNow.isSuccess}
          className="mt-2 rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {checkNow.isSuccess ? "Checking…" : "Check it now"}
        </button>
        {checkNow.isError && (
          <p className="mt-1 text-sm text-red">{checkNow.error.message}</p>
        )}
      </div>
    );
  }
  // Questions Homing remembers for every opportunity (age, languages, country) come first;
  // the ones only this opportunity needs come after.
  const questions = [
    ...answer.questions.filter((q) => !q.id.startsWith("rule:")),
    ...answer.questions.filter((q) => q.id.startsWith("rule:")),
  ];
  const host = answer.officialUrl ? hostOf(answer.officialUrl) : null;
  const verdict = VERDICT[answer.verdict];
  const failing = answer.rules.filter(
    (r) => r.strength === "required" && r.result === "fails",
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {verdict && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${verdict.tone}`}
          >
            {verdict.label}
          </span>
        )}
        {host && !answer.note && (
          <span className="text-sm text-ink-2">
            Checked against{" "}
            <a
              href={answer.officialUrl!}
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              {host}
            </a>
          </span>
        )}
      </div>
      {answer.verdict === "closed" && (
        <p className="font-semibold">
          {answer.fromPost || !answer.officialUrl
            ? "Closed, going by the date in the post."
            : "Closed, per the official page."}
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
      {answer.verdict === "fits_you" && (
        <p>Nothing on the official page rules you out.</p>
      )}
      {answer.fromPost &&
        answer.verdict === "couldnt_confirm" &&
        answer.rules.length > 0 &&
        answer.rules.every(
          (r) => r.strength !== "required" || r.result === "meets",
        ) && <p>Going by the post, nothing rules you out.</p>}
      {answer.note && <p className="text-amber">{answer.note}</p>}

      {questions.length > 0 && (
        <div className="space-y-3 rounded-xl bg-amber-soft/60 p-3">
          <p className="text-sm text-ink-2">
            Answer {questions.length === 1 ? "this" : "these"} to see if it fits
            you.
            {questions.some((q) => !q.id.startsWith("rule:")) &&
              " Homing remembers, so other opportunities won't ask again."}
          </p>
          {questions
            .slice(0, showAll ? undefined : FIRST_QUESTIONS)
            .map((q) => (
              <QuestionView
                key={q.id}
                question={q}
                busy={reply.isPending}
                onAnswer={(value) => reply.mutate({ id: q.id, value })}
              />
            ))}
          {!showAll && questions.length > FIRST_QUESTIONS && (
            <button
              type="button"
              onClick={() => setShowAll(true)}
              className="text-sm text-ink-2 underline"
            >
              Show {questions.length - FIRST_QUESTIONS} more{" "}
              {questions.length - FIRST_QUESTIONS === 1
                ? "question"
                : "questions"}
            </button>
          )}
        </div>
      )}
      {summary && <p className="text-sm font-semibold text-green">{summary}</p>}
      {reply.isError && (
        <p className="text-sm text-amber">{reply.error.message}</p>
      )}

      {answer.findings.length > 0 && (
        <ul className="space-y-2.5">
          {answer.findings
            .slice(0, showFindings ? undefined : FIRST_FINDINGS)
            .map((f, i) => (
              <li key={i}>
                <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                  {answer.samePage && f.kind === "left_out"
                    ? "On the official page"
                    : (FINDING_KIND[f.kind] ?? f.kind)}
                </p>
                <p>{f.point}</p>
                <blockquote className="mt-1 border-l-2 border-green pl-2.5 text-sm text-ink-2">
                  “{f.quote}”
                  {host && (
                    <span className="mt-0.5 block text-xs text-green">
                      Found word for word on {host}
                    </span>
                  )}
                </blockquote>
              </li>
            ))}
          {!showFindings && answer.findings.length > FIRST_FINDINGS && (
            <li>
              <button
                type="button"
                onClick={() => setShowFindings(true)}
                className="text-sm text-ink-2 underline"
              >
                Show {answer.findings.length - FIRST_FINDINGS} more
              </button>
            </li>
          )}
        </ul>
      )}
      {answer.items.length > 0 && <ItemsView items={answer.items} />}

      {answer.rules.length > 0 && (
        <details className="group rounded-2xl bg-grey-soft/60 px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm">
            <span>
              <span className="font-semibold">Who can apply</span>
              <span className="text-ink-2"> · {ruleSummary(answer.rules)}</span>
            </span>
            <span className="text-xs text-muted group-open:hidden">Show</span>
            <span className="hidden text-xs text-muted group-open:inline">
              Hide
            </span>
          </summary>
          <ul className="mt-2 space-y-2">
            {answer.rules.map((r, i) => {
              const result = RESULT[r.result] ?? RESULT.unknown;
              return (
                <li key={i} className="grid grid-cols-[18px_1fr] gap-1.5">
                  <span
                    className={`font-bold ${result.tone}`}
                    title={result.words}
                    aria-label={result.words}
                  >
                    {result.mark}
                  </span>
                  <div>
                    <p>
                      {r.plain.replace(/\s*\(preferred\)\s*$/i, "")}
                      {r.strength === "preferred" && (
                        <span className="text-muted">
                          {" "}
                          · preferred, not required
                        </span>
                      )}
                    </p>
                    <p className="text-xs text-ink-2">
                      “{r.quote}”
                      {host && <span className="text-green"> · on {host}</span>}
                      {answer.fromPost && (
                        <span className="text-muted">
                          {" "}
                          · in the post, not confirmed
                        </span>
                      )}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </details>
      )}

      {answer.deadline ? (
        <p className="text-sm">
          Official closing date: {answer.deadline.display}
          {!answer.deadline.tzStated && (
            <span className="text-muted"> · time zone not stated</span>
          )}
        </p>
      ) : host && postHasDeadline && !answer.note ? (
        <p className="text-sm text-ink-2">
          We didn&apos;t find a closing date on the official page.
        </p>
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
          <Link
            href={`/threads/${thread.id}`}
            className="font-semibold hover:underline"
          >
            {thread.title}
          </Link>
          {thread.count > 1
            ? `: your ${ordinal(thread.position)} save on this.`
            : ": the first save on this."}
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
          <span
            className="select-none font-mono text-sm tracking-widest text-muted blur-[3px]"
            aria-hidden
          >
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
          <p className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-sm">
            {text}
          </p>
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
              {COPY_KIND[copy.kind] ?? copy.kind} ·{" "}
              {copy.chars.toLocaleString("en-GB")} characters
              {copy.sourceUrl && (
                <>
                  {" · "}
                  <a
                    href={copy.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
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

const PASTE = {
  transcript: {
    offer: "YouTube didn't share this video's captions with us.",
    button: "Paste its transcript",
    after: "and Homing can point to the exact second.",
    how: (
      <>
        On YouTube, open the video, choose <b>…</b> then <b>Show transcript</b>, select it all
        and copy it here.
      </>
    ),
    placeholder: "0:00\nWelcome back to the channel…",
    label: "The video's transcript",
    submit: "Add transcript",
  },
  page: {
    offer: "Homing couldn't read this link itself.",
    button: "Paste what it says",
    after: "and every agent carries on from your copy.",
    how: <>Open the link, select the text that matters and copy it here.</>,
    placeholder: "Applications are open until…",
    label: "The page's text",
    submit: "Add the text",
  },
};

/** What Homing can't fetch itself, the person can copy. A video's transcript: YouTube shares
 * captions only with a video's owner; Homing reads it with its timestamps. A page's text: the
 * site asks programs not to read it, or it's a post Homing can't see inside. */
function PasteText({ saveId, kind }: { saveId: string; kind: keyof typeof PASTE }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const words = PASTE[kind];
  const paste = useMutation({
    mutationFn: async () => {
      if (kind === "page") {
        await savesApi.pastePageText(saveId, text);
        return "Got it. Reading it now…";
      }
      const { lines } = await savesApi.pasteTranscript(saveId, text);
      return `Got ${lines} timed lines. Reading the video again with them…`;
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["save", saveId] }),
  });
  if (paste.isSuccess) {
    return <p className="mt-2 text-sm text-ink-2">{paste.data}</p>;
  }
  if (!open) {
    return (
      <p className="mt-2 text-sm text-ink-2">
        {words.offer}{" "}
        <button type="button" onClick={() => setOpen(true)} className="font-semibold underline">
          {words.button}
        </button>{" "}
        {words.after}
      </p>
    );
  }
  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim().length >= 20) paste.mutate();
      }}
    >
      <p className="text-sm text-ink-2">{words.how}</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder={words.placeholder}
        aria-label={words.label}
        className="w-full rounded-2xl border border-line bg-white/70 p-3 text-sm outline-none focus:border-ink/30"
      />
      {paste.isError && <p className="text-sm text-red">{paste.error.message}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={text.trim().length < 20 || paste.isPending}
          className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {paste.isPending ? "Reading…" : words.submit}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-full px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

function Card({ card }: { card: SaveCard }) {
  const { save, what, copies, pending } = card;
  const isPrivate = save.visibility === "private";
  const paused = !what && save.status !== "failed" && save.error;
  const title = isPrivate
    ? "Private save"
    : (what?.title ??
      save.label ??
      (save.url ? hostOf(save.url) : save.text?.slice(0, 80)) ??
      "Your save");
  // Amounts and requirements only mean something on an opportunity; on a talk they're stray numbers.
  const facts = [
    // "closes TOMORROW" was true the day it was posted; When will you need it? gives the date.
    ...(what?.keyFacts.dates ?? [])
      .map((d) => d.text)
      .filter((t) => !/\b(today|tonight|tomorrow|yesterday)\b/i.test(t)),
    ...(what?.isOpportunity
      ? (what.keyFacts.amounts ?? []).map((a) => a.text)
      : []),
    ...(what?.isOpportunity
      ? (what.keyFacts.requirements ?? []).map((r) => r.text)
      : []),
  ].slice(0, 6);

  return (
    <article className="glass rounded-[var(--radius-card)] p-5">
      <p className="text-xs text-muted">
        Saved {savedOn(save.savedAt)}
        {save.platform && ` · ${PLATFORM[save.platform] ?? save.platform}`}
        {isPrivate && " · Private"}
      </p>
      <h1 className="font-display mt-1 text-[22px] font-bold leading-snug tracking-[-0.02em]">
        {title}
      </h1>
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
      {save.files > 0 && !isPrivate && (
        <Files saveId={save.id} kind={save.kind} count={save.files} />
      )}

      <div className="mt-4">
        <AnswerRow answer="what" by={isPrivate ? undefined : card.by.what}>
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
                    <li
                      key={f}
                      className="rounded-full bg-grey-soft px-2.5 py-0.5 text-xs text-ink-2"
                    >
                      {f}
                    </li>
                  ))}
                </ul>
              )}
              {save.platform === "youtube" &&
                !copies.some((c) => c.kind === "transcript") && (
                  <PasteText saveId={save.id} kind="transcript" />
                )}
              {save.kind === "link" && save.platform !== "youtube" && copies.length === 0 && (
                <PasteText saveId={save.id} kind="page" />
              )}
            </>
          ) : save.status === "failed" ? (
            <p className="text-amber">
              {save.error ?? "Couldn't read this save."}
            </p>
          ) : paused ? (
            <p className="text-amber">{save.error}</p>
          ) : (
            <Working text="Reading it…" />
          )}
        </AnswerRow>
        {(["true", "for", "when"] as const).map((answer) => (
          <AnswerRow
            key={answer}
            answer={answer}
            by={isPrivate || pending.includes(answer) ? undefined : card.by[answer]}
          >
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
                postHasDeadline={(what?.keyFacts.dates ?? []).some(
                  (d) => d.role === "deadline",
                )}
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
      q.state.data &&
      q.state.data.pending.length > 0 &&
      !q.state.data.save.error
        ? 3000
        : false,
  });

  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.saveId === id)
        void queryClient.invalidateQueries({ queryKey: ["save", id] });
    },
    [id, queryClient],
  );
  useEventStream(onEvent);

  if (isPending) return <Loading label="Opening your save…" />;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  return <Card card={data} />;
}
