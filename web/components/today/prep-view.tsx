"use client";

import { useQuery } from "@tanstack/react-query";
import { ListChecks, Play } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { type PrepSheet, type SheetItem, todayApi } from "@/lib/api";
import { Loading } from "@/components/shell/loading";

const LIVE = ["queued", "working"];

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function youtubeId(url: string): string | null {
  const m =
    url.match(/[?&]v=([\w-]{6,})/) ??
    url.match(/(?:youtu\.be|shorts|embed)\/([\w-]{6,})/);
  return m ? m[1] : null;
}

type Clip = { video: string; start: number; end?: number };

/** A YouTube player that plays one clip, or a reel of clips one after another. */
function Player({
  sheet,
  clips,
  onDone,
}: {
  sheet: PrepSheet;
  clips: Clip[];
  onDone: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [index, setIndex] = useState(0);
  const clip = clips[index];
  const id = clip ? youtubeId(sheet.videos[clip.video]?.url ?? "") : null;

  // YouTube posts its state to the page; "ended" (0) at a clip's end moves the reel on.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (!String(e.origin).includes("youtube")) return;
      let data: { event?: string; info?: unknown } = {};
      try {
        data = typeof e.data === "string" ? JSON.parse(e.data) : e.data;
      } catch {
        return;
      }
      const ended =
        (data.event === "onStateChange" && data.info === 0) ||
        (data.event === "infoDelivery" &&
          (data.info as { playerState?: number } | null)?.playerState === 0);
      if (!ended) return;
      if (index + 1 < clips.length) setIndex(index + 1);
      else onDone();
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [clips.length, index, onDone]);

  if (!clip || !id) return null;
  const end = clip.end ? `&end=${clip.end}` : "";
  const src = `https://www.youtube-nocookie.com/embed/${id}?start=${clip.start}${end}&autoplay=1&rel=0&enablejsapi=1`;
  return (
    <div className="glass sticky top-3 z-10 mb-5 overflow-hidden rounded-[var(--radius-card)]">
      <iframe
        ref={frame}
        key={`${index}-${src}`}
        src={src}
        title={sheet.videos[clip.video]?.title ?? "Video"}
        className="aspect-video w-full"
        allow="autoplay; encrypted-media; picture-in-picture"
        allowFullScreen
        onLoad={() =>
          frame.current?.contentWindow?.postMessage(
            JSON.stringify({ event: "listening", id: 1, channel: "widget" }),
            "*",
          )
        }
      />
      <p className="px-4 py-2 text-sm text-ink-2">
        {clips.length > 1 && `${index + 1} of ${clips.length} · `}
        <span className="font-semibold text-ink">
          {sheet.videos[clip.video]?.title}
        </span>{" "}
        from {clock(clip.start)}
      </p>
    </div>
  );
}

function Line({
  item,
  sheet,
  play,
}: {
  item: SheetItem;
  sheet: PrepSheet;
  play: (c: Clip) => void;
}) {
  return (
    <li className="py-2">
      <p className="text-[15px]">{item.text}</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {item.cites.map((c) => {
          const video = sheet.videos[c.video];
          if (!video) return null;
          const point = video.points.find((p) => p.tStart === c.t);
          return (
            <button
              key={`${c.video}-${c.t}`}
              type="button"
              onClick={() => play({ video: c.video, start: c.t })}
              title={point ? `"${point.quote}"` : undefined}
              className="flex max-w-full items-center gap-1 rounded-full bg-grey-soft px-2.5 py-1 text-xs font-semibold text-ink-2 hover:bg-ink hover:text-white"
            >
              <Play className="size-3 shrink-0" aria-hidden />
              <span className="truncate">{video.title}</span>
              <span className="shrink-0">· {clock(c.t)}</span>
            </button>
          );
        })}
      </div>
    </li>
  );
}

/** A prep card: what your saved videos say for the moment coming up, each at its second. */
export function PrepView() {
  const { id } = useParams<{ id: string }>();
  const [clips, setClips] = useState<Clip[]>([]);
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["card", id],
    queryFn: () => todayApi.card(id),
    refetchInterval: (q) =>
      LIVE.includes(q.state.data?.sheet?.status ?? "queued") ? 3000 : false,
    refetchIntervalInBackground: true,
  });
  const stop = useCallback(() => setClips([]), []);

  if (isPending) return <Loading label="Opening this card…" />;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  const sheet = data.sheet;
  const reelSeconds = (sheet?.reel ?? []).reduce(
    (n, r) => n + r.end - r.start,
    0,
  );
  const used = Object.keys(sheet?.videos ?? {}).length;

  return (
    <article>
      <Link href="/today" className="text-sm text-ink-2 hover:underline">
        ← Today
      </Link>
      <p className="mt-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.07em] text-amber">
        <ListChecks className="size-3.5" aria-hidden />
        {data.whyNow}
      </p>
      <h1 className="font-display mt-1 text-[26px] font-extrabold leading-tight tracking-[-0.03em]">
        {data.title}
      </h1>

      {!sheet || LIVE.includes(sheet.status) ? (
        <p className="mt-4 text-ink-2">
          Going through your videos for this, one by one. Each step shows up in{" "}
          <Link href="/agents" className="font-semibold hover:underline">
            Your agents
          </Link>
          .
        </p>
      ) : sheet.status === "failed" ? (
        <p className="mt-4 text-ink-2">
          Couldn&apos;t make this sheet. Try again later.
        </p>
      ) : (
        <>
          {sheet.reel.length > 0 && (
            <button
              type="button"
              onClick={() => setClips(sheet.reel)}
              className="mt-4 flex items-center gap-1.5 rounded-full bg-red px-4 py-2 text-sm font-semibold text-white"
            >
              <Play className="size-4" aria-hidden />
              Play the best moments ({clock(reelSeconds)})
            </button>
          )}
          <div className="mt-4">
            {clips.length > 0 && (
              <Player sheet={sheet} clips={clips} onDone={stop} />
            )}
          </div>

          {sheet.checklist.length === 0 ? (
            <p className="text-ink-2">
              None of your videos had steps for this that I could point to at a
              second.
            </p>
          ) : (
            <section className="glass rounded-[var(--radius-card)] p-5">
              <h2 className="font-display text-lg font-bold">
                Before you start: {sheet.checklist.length} steps
              </h2>
              <ol className="mt-1 list-decimal divide-y divide-grey-soft pl-5">
                {sheet.checklist.map((item) => (
                  <Line
                    key={item.text}
                    item={item}
                    sheet={sheet}
                    play={(c) => setClips([c])}
                  />
                ))}
              </ol>
            </section>
          )}

          {sheet.agree.length > 0 && (
            <section className="glass mt-4 rounded-[var(--radius-card)] p-5">
              <h2 className="font-display text-lg font-bold">
                Your videos agree
              </h2>
              <ul className="mt-1 divide-y divide-grey-soft">
                {sheet.agree.map((item) => (
                  <Line
                    key={item.text}
                    item={item}
                    sheet={sheet}
                    play={(c) => setClips([c])}
                  />
                ))}
              </ul>
            </section>
          )}

          {sheet.disagree.length > 0 && (
            <section className="glass mt-4 rounded-[var(--radius-card)] p-5">
              <h2 className="font-display text-lg font-bold">
                Where they differ
              </h2>
              {sheet.disagree.map((d) => (
                <div key={d.topic} className="mt-2">
                  <p className="text-sm font-semibold text-ink-2">{d.topic}</p>
                  <ul className="divide-y divide-grey-soft">
                    {d.sides.map((item) => (
                      <Line
                        key={item.text}
                        item={item}
                        sheet={sheet}
                        play={(c) => setClips([c])}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          )}

          <p className="mt-4 text-sm text-muted">
            From {used} of your videos. Every point was found in the
            video&apos;s captions at that second
            {sheet.droppedPoints > 0 &&
              `; ${sheet.droppedPoints} ${sheet.droppedPoints === 1 ? "that wasn't was" : "that weren't were"} left out`}
            .
            {sheet.skipped.noCaptions > 0 &&
              ` ${sheet.skipped.noCaptions} videos have no captions yet.`}
            {sheet.skipped.reels > 0 &&
              ` ${sheet.skipped.reels} reels can't be read from a link.`}
          </p>
        </>
      )}
    </article>
  );
}
