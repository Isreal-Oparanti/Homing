"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CalendarPlus, Check, Clock, Copy, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { FoundForYou } from "@/components/finds/found-for-you";
import { EmptyState } from "@/components/shell/empty-state";
import { Loading } from "@/components/shell/loading";
import { type AgentEvent, meApi, type Moment, type TodayCard, todayApi } from "@/lib/api";
import { useEventStream } from "@/lib/events";

/** "Something coming up?": the person's own moments, and the goals each one needs. */
function Moments({ moments }: { moments: Moment[] }) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const add = useMutation({
    mutationFn: () => todayApi.addMoment(text.trim()),
    onSuccess: () => {
      setText("");
      void queryClient.invalidateQueries({ queryKey: ["today"] });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => todayApi.removeMoment(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["today"] }),
  });

  return (
    <section className="glass mb-5 rounded-[var(--radius-card)] p-4">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim().length >= 3) add.mutate();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Something coming up? e.g. recording my demo on Tuesday evening"
          aria-label="Something coming up"
          className="min-w-0 flex-1 bg-transparent px-1 outline-none placeholder:text-muted"
        />
        <button
          type="submit"
          disabled={text.trim().length < 3 || add.isPending}
          className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {add.isPending ? "Adding…" : "Add"}
        </button>
      </form>
      {add.isError && <p className="mt-1 text-sm text-red">{add.error.message}</p>}
      {moments.length > 0 && (
        <ul className="mt-3 space-y-2">
          {moments.map((m) => (
            <li key={m.id} className="flex items-start gap-2 text-sm">
              <Clock className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
              <div className="min-w-0 flex-1">
                <p>
                  <span className="font-semibold">{m.text}</span>
                  <span className="text-ink-2"> · {m.display}</span>
                </p>
                <p className="text-ink-2">
                  {m.threads.length > 0 ? (
                    <>
                      Goes with{" "}
                      {m.threads.map((t, i) => (
                        <span key={t.id}>
                          {i > 0 && ", "}
                          <Link href={`/threads/${t.id}`} className="font-semibold hover:underline">
                            {t.title}
                          </Link>
                        </span>
                      ))}
                    </>
                  ) : (
                    "Looking for the goals it needs…"
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={() => remove.mutate(m.id)}
                aria-label={`Remove ${m.text}`}
                className="rounded-full p-1 text-muted hover:bg-grey-soft"
              >
                <X className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Homing has no push: your phone's calendar brings saves back when you're not in the app. */
function CalendarFeed() {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const feed = useQuery({ queryKey: ["calendar-feed"], queryFn: () => meApi.calendar(), enabled: open });
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mb-5 flex items-center gap-1.5 px-1 text-sm font-semibold text-ink-2 hover:text-ink"
      >
        <CalendarPlus className="size-4" aria-hidden />
        Get these on your phone&apos;s calendar
      </button>
    );
  }
  return (
    <section className="glass mb-5 rounded-[var(--radius-card)] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">Your saves, in your calendar</p>
          <p className="mt-0.5 text-sm text-ink-2">
            Add this once. Every date and moment then arrives with your phone&apos;s own reminder,
            and opens back here.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close"
          className="rounded-full p-1 text-muted hover:bg-grey-soft"
        >
          <X className="size-4" />
        </button>
      </div>
      {feed.isPending && <p className="mt-3 text-sm text-ink-2">Making your link…</p>}
      {feed.isError && <p className="mt-3 text-sm text-red">{feed.error.message}</p>}
      {feed.data && (
        <>
          <div className="mt-3 flex flex-wrap gap-2">
            <a
              href={feed.data.googleUrl}
              target="_blank"
              rel="noreferrer"
              className="rounded-full bg-ink px-4 py-1.5 text-sm font-semibold text-white"
            >
              Add to Google Calendar
            </a>
            <a href={feed.data.webcalUrl} className="glass rounded-full px-4 py-1.5 text-sm font-semibold">
              Apple or phone calendar
            </a>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(feed.data.httpsUrl).then(() => setCopied(true));
              }}
              className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
            >
              {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
              {copied ? "Copied" : "Copy link"}
            </button>
          </div>
          <p className="mt-2 text-xs text-muted">
            Your calendar checks for changes about every hour; Google Calendar can take a few hours.
            The link is private: anyone who has it can see your saved dates.
          </p>
        </>
      )}
    </section>
  );
}

/** Google Calendar opens with the event filled in (no file); Apple and Outlook take the
 * calendar file, which a phone opens straight into "Add event". */
function AddToCalendar({ saveId, title, dueAt, why }: { saveId: string; title: string; dueAt: string; why: string }) {
  const [open, setOpen] = useState(false);
  const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
  const start = new Date(dueAt);
  const end = new Date(start.getTime() + 30 * 60 * 1000);
  const google =
    "https://calendar.google.com/calendar/render?action=TEMPLATE" +
    `&text=${encodeURIComponent(title)}` +
    `&dates=${stamp(start)}/${stamp(end)}` +
    `&details=${encodeURIComponent(`${why}\n\nOpen it in Homing: ${window.location.origin}/saves/${saveId}`)}`;
  return (
    <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex items-center gap-1 text-sm font-semibold text-ink-2 hover:underline"
      >
        <CalendarPlus className="size-4" aria-hidden />
        Add to calendar
      </button>
      {open && (
        <div className="flex basis-full flex-wrap justify-end gap-2 text-sm">
          <a
            href={google}
            target="_blank"
            rel="noreferrer"
            onClick={() => setOpen(false)}
            className="rounded-full bg-ink px-3.5 py-1.5 font-semibold text-white"
          >
            Google Calendar
          </a>
          <a
            href={`/api/backend/saves/${saveId}/calendar.ics`}
            onClick={() => setOpen(false)}
            className="glass rounded-full px-3.5 py-1.5 font-semibold"
          >
            Apple or Outlook
          </a>
        </div>
      )}
    </div>
  );
}

function Card({ card }: { card: TodayCard }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const act = useMutation({
    mutationFn: (action: "use" | "dismiss" | "later") => todayApi.act(card.id, action),
    onSuccess: (_, action) => {
      void queryClient.invalidateQueries({ queryKey: ["today"] });
      if (action === "use") {
        router.push(card.saveId ? `/saves/${card.saveId}` : `/cards/${card.id}`);
      }
    },
  });
  const prep = card.kind === "prep";
  return (
    <li className="glass rounded-[var(--radius-card)] p-5">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.07em] text-amber">
        {prep ? <Sparkles className="size-3.5" aria-hidden /> : <CalendarClock className="size-3.5" aria-hidden />}
        {card.whyNow}
      </p>
      <p className="font-display mt-1 text-lg font-bold leading-snug tracking-[-0.02em]">{card.title}</p>
      <p className="mt-1 text-[15px]">{card.nextStep}</p>
      {!prep && (card.unconfirmed || !card.tzStated) && (
        <p className="mt-1 text-xs text-muted">
          {card.unconfirmed && "The date is from the post, not the official page"}
          {card.unconfirmed && !card.tzStated && " · "}
          {!card.tzStated && "time zone not stated"}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          // A prep card stays on Today until the moment: opening it isn't being done with it.
          onClick={() => (prep ? router.push(`/cards/${card.id}`) : act.mutate("use"))}
          disabled={act.isPending}
          className="rounded-full bg-red px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          Open
        </button>
        <button
          type="button"
          onClick={() => act.mutate("later")}
          disabled={act.isPending}
          className="glass rounded-full px-4 py-1.5 text-sm font-semibold"
        >
          Later
        </button>
        <button
          type="button"
          onClick={() => act.mutate("dismiss")}
          disabled={act.isPending}
          className="rounded-full px-3 py-1.5 text-sm font-semibold text-ink-2 hover:bg-grey-soft"
        >
          Dismiss
        </button>
        {card.saveId && card.dueAt && (
          <AddToCalendar saveId={card.saveId} title={card.title} dueAt={card.dueAt} why={card.whyNow} />
        )}
      </div>
      {act.isError && <p className="mt-1 text-sm text-red">{act.error.message}</p>}
    </li>
  );
}

/** At most three things that need you now, chosen by When will you need it?. */
export function TodayList() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["today"],
    queryFn: () => todayApi.get(),
  });

  const onEvent = useCallback(
    (event: AgentEvent) => {
      if (event.agent === "when" || event.agent === "true") {
        void queryClient.invalidateQueries({ queryKey: ["today"] });
      }
    },
    [queryClient],
  );
  useEventStream(onEvent);

  if (isPending) return <Loading label="Looking at what's coming up…" lines={3} />;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  return (
    <>
      <Moments moments={data.moments} />
      <CalendarFeed />
      {data.cards.length === 0 ? (
        <EmptyState
          title="Nothing needs you right now."
          body={
            data.comingBack.length > 0
              ? "Your saves come back here the morning they matter, with the next step. Here's what's next."
              : "When something you saved matters, it comes back here with the next step. Tell Homing what's coming up, and it gets your saves ready."
          }
        />
      ) : (
        <ul className="space-y-3">
          {data.cards.map((card) => (
            <Card key={card.id} card={card} />
          ))}
        </ul>
      )}
      <FoundForYou />
      {data.comingBack.length > 0 && (
        <section className="mt-5">
          <h2 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.07em] text-muted">
            Coming back
          </h2>
          <ul className="glass divide-y divide-line rounded-[var(--radius-card)] px-5">
            {data.comingBack.map((c) => (
              <li key={c.saveId}>
                <Link href={`/saves/${c.saveId}`} className="flex items-start gap-3 py-3.5 hover:underline">
                  <CalendarClock className="mt-0.5 size-4 shrink-0 text-amber" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold leading-snug">{c.title}</span>
                    <span className="block text-sm text-ink-2">
                      Back on {c.backOn} · for {c.due}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
