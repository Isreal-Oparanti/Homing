"use client";

import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, CircleX, FileText, Search } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { type AskStatus, askApi } from "@/lib/api";
import { Loading } from "@/components/shell/loading";
import { ByLine } from "@/components/team/by-line";

function savedOn(iso: string): string {
  const d = new Date(iso);
  return `${d.getDate()} ${d.toLocaleString("en-GB", { month: "short" })} ${d.getFullYear()}`;
}

/** One answer page: points from your own saves, each quote checked against the save. */
const STEP_ICON = { search: Search, open: FileText, refused: CircleX, accepted: BadgeCheck };
const STEP_TONE = { search: "text-ink-2", open: "text-ink-2", refused: "text-amber", accepted: "text-green" };

/** Muse Wonder's steps and code's checks, in the order they happened. */
function Steps({ steps, live = false }: { steps: AskStatus["steps"]; live?: boolean }) {
  if (steps.length === 0) return null;
  return (
    <ol className="mt-2 space-y-1.5">
      {steps.map((step, i) => {
        const Icon = STEP_ICON[step.kind] ?? Search;
        const newest = live && i === steps.length - 1;
        return (
          <li key={i} className={`flex items-start gap-2 text-sm ${newest ? "animate-pulse" : ""}`}>
            <Icon className={`mt-0.5 size-4 shrink-0 ${STEP_TONE[step.kind] ?? "text-ink-2"}`} aria-hidden />
            <span className={step.kind === "refused" ? "text-amber" : "text-ink-2"}>{step.text}</span>
          </li>
        );
      })}
    </ol>
  );
}

export function AskView() {
  const { id } = useParams<{ id: string }>();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["ask", id],
    queryFn: () => askApi.get(id),
    refetchInterval: (q) => (q.state.data?.status === "working" ? 1500 : false),
    // Keep checking while the person looks at another tab or app: the answer is short-lived work.
    refetchIntervalInBackground: true,
  });

  if (isPending) return <Loading label="Opening your question…" />;
  if (isError) return <p className="text-ink-2">{error.message}</p>;

  return (
    <article>
      <Link href="/search" className="text-sm text-ink-2 hover:underline">
        ← Search and ask
      </Link>
      <h1 className="mt-2 font-display text-2xl font-bold tracking-[-0.02em]">{data.question}</h1>

      {data.status === "working" && (
        <section className="glass mt-3 rounded-[var(--radius-card)] px-4 py-3">
          <p className="text-sm font-semibold">
            {data.steps.length
              ? "Working on it, step by step"
              : "Finding the saves that answer this, reading them, and checking every quote…"}
          </p>
          {data.steps.length > 0 && <ByLine models={["muse-wonder-1.0"]} how="choosing each step itself" />}
          <Steps steps={data.steps} live />
        </section>
      )}
      {data.status === "failed" && <p className="mt-3 text-red">{data.error}</p>}

      {data.status === "done" && (
        <>
          <p className="mt-1 text-sm text-muted">
            From your own saves: looked at {data.considered}, read {data.read}. Every quote below was found word for
            word in the save it cites.
          </p>
          {data.agent && (
            <section className="glass mt-3 rounded-[var(--radius-card)] px-4 py-3">
              <p className="text-sm font-semibold">How it was found</p>
              <ByLine
                models={[data.agent.model]}
                how={`searched ${data.agent.searches.length} ${
                  data.agent.searches.length === 1 ? "way" : "ways"
                } and opened ${data.agent.opened} ${data.agent.opened === 1 ? "save" : "saves"}, choosing each step itself`}
              />
              {data.steps.length > 0 ? (
                <Steps steps={data.steps} />
              ) : (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {data.agent.searches.map((q) => (
                    <li key={q} className="rounded-full bg-grey-soft px-2.5 py-0.5 text-xs text-ink-2">
                      &ldquo;{q}&rdquo;
                    </li>
                  ))}
                </ul>
              )}
              <ByLine
                models={[]}
                how={
                  data.agent.refusals
                    ? `refused ${data.agent.refusals} ${
                        data.agent.refusals === 1 ? "answer" : "answers"
                      } with quotes that didn't hold up, and sent ${
                        data.agent.refusals === 1 ? "it" : "them"
                      } back to fix`
                    : "checked every quote word for word before showing the answer"
                }
              />
            </section>
          )}

          {data.points.length > 0 && (
            <ol className="mt-4 space-y-3">
              {data.points.map((p, i) => (
                <li key={i} className="glass rounded-[var(--radius-card)] px-4 py-3">
                  <p className="font-semibold">{p.point}</p>
                  <blockquote className="mt-1.5 border-l-2 border-red pl-3 text-sm text-ink-2">
                    &ldquo;{p.quote}&rdquo;
                  </blockquote>
                  <p className="mt-1.5 flex items-center gap-1 text-xs text-muted">
                    <BadgeCheck className="size-3.5 text-green" aria-label="Quote checked" />
                    <Link href={`/saves/${p.saveId}`} className="font-semibold hover:underline">
                      {p.title}
                    </Link>
                    <span>· saved {savedOn(p.savedAt)}</span>
                  </p>
                </li>
              ))}
            </ol>
          )}

          {data.also.length > 0 && (
            <section className="mt-5">
              <h2 className="font-semibold">Also in your saves</h2>
              <p className="text-sm text-ink-2">These look relevant, but Homing could only see their titles. Open them.</p>
              <ul className="mt-1.5 space-y-1">
                {data.also.map((x) => (
                  <li key={x.saveId}>
                    <Link href={`/saves/${x.saveId}`} className="text-sm font-semibold hover:underline">
                      {x.title}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {data.notCovered.length > 0 && (
            <section className="mt-5">
              <h2 className="font-semibold">Not in your saves</h2>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-ink-2">
                {data.notCovered.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </article>
  );
}
