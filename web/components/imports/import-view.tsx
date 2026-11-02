"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileArchive, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { type ImportStatus, importApi } from "@/lib/api";

const LIVE: ImportStatus["status"][] = ["received", "importing"];

function mb(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** The import's progress, then what came in. */
function Progress({ imp }: { imp: ImportStatus }) {
  const c = imp.counts;
  if (imp.status === "failed") {
    return <p className="text-sm text-red">{imp.error ?? "The import stopped. Try again."}</p>;
  }
  if (imp.status !== "done") {
    const pct = c.total ? Math.round(((c.done ?? 0) / c.total) * 100) : 0;
    return (
      <div>
        <p className="text-sm font-semibold">
          {c.total ? `Making saves… ${c.done ?? 0} of ${c.total}` : "Opening your export…"}
        </p>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-grey-soft">
          <div className="h-full rounded-full bg-red transition-[width]" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }
  const left = c.skipped ?? 0;
  return (
    <div>
      <p className="font-semibold">
        {plural(c.saves ?? 0, "save")} from {plural(c.messages ?? 0, "message")}.
      </p>
      <ul className="mt-2 space-y-1 text-sm text-ink-2">
        {(c.media ?? 0) > 0 && <li>{plural(c.media ?? 0, "file")} stored: photos, videos, voice notes and documents.</li>}
        {(c.private ?? 0) > 0 && (
          <li>{plural(c.private ?? 0, "save")} kept private, because they look like passwords, codes or account numbers. Homing never sends those to AI.</li>
        )}
        {(c.duplicates ?? 0) > 0 && <li>{plural(c.duplicates ?? 0, "save")} you had saved before. Saving again is a signal, so they&apos;re kept.</li>}
        {left > 0 && <li>{plural(left, "message")} left out: stickers, contact cards, empty messages, and media the export didn&apos;t include.</li>}
        {(c.already ?? 0) > 0 && <li>{plural(c.already ?? 0, "save")} already imported before, so not added again.</li>}
      </ul>
      <p className="mt-3 text-sm">
        Homing is reading them now, a few at a time. Watch it happen in{" "}
        <Link href="/team" className="font-semibold underline">
          The team
        </Link>
        , or see where they went in{" "}
        <Link href="/threads" className="font-semibold underline">
          Threads
        </Link>
        .
      </p>
    </div>
  );
}

/** Bring a whole WhatsApp "message yourself" chat in at once. */
export function ImportView() {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [sent, setSent] = useState<number | null>(null); // upload progress, 0 to 1
  const [error, setError] = useState<string | null>(null);
  const [current, setCurrent] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  // After a refresh, pick up the latest import.
  const recent = useQuery({ queryKey: ["imports"], queryFn: () => importApi.recent() });
  const id = current ?? recent.data?.[0]?.id ?? null;
  const status = useQuery({
    queryKey: ["import", id],
    queryFn: () => importApi.get(id!),
    enabled: id !== null,
    refetchInterval: (q) => (q.state.data && !LIVE.includes(q.state.data.status) ? false : 2000),
    refetchIntervalInBackground: true,
  });

  const pick = (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    setError(null);
    setFile(f);
  };

  const send = async () => {
    if (!file) return;
    setError(null);
    setSent(0);
    try {
      const imp = await importApi.upload(file, setSent);
      setCurrent(imp.id);
      setFile(null);
      queryClient.setQueryData(["import", imp.id], imp);
      void queryClient.invalidateQueries({ queryKey: ["imports"] });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send the export. Try again.");
    } finally {
      setSent(null);
    }
  };

  const uploading = sent !== null;
  const imp = status.data;

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files);
        }}
        className={`glass rounded-[var(--radius-card)] p-5 ${dragging ? "ring-2 ring-red" : ""}`}
      >
        <h2 className="font-semibold">Export the chat from WhatsApp</h2>
        <ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-ink-2">
          <li>Open the chat you save things to (often the one with yourself).</li>
          <li>
            <span className="font-semibold">Android:</span> tap ⋮, then More, then Export chat, then Include media.{" "}
            <span className="font-semibold">iPhone:</span> tap the name at the top, then Export Chat, then Attach Media.
          </li>
          <li>Save the .zip it makes, then choose it here. The chat .txt alone works too, without the files.</li>
        </ol>

        <input
          ref={input}
          type="file"
          accept=".zip,.txt,application/zip,text/plain"
          className="hidden"
          onChange={(e) => pick(e.target.files)}
        />
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={uploading}
            className="glass flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold disabled:opacity-60"
          >
            <FileArchive className="size-4" aria-hidden />
            {file ? "Choose another" : "Choose the export"}
          </button>
          {file && (
            <button
              type="button"
              onClick={send}
              disabled={uploading}
              className="flex items-center gap-2 rounded-full bg-red px-5 py-2 text-sm font-semibold text-white shadow-[0_6px_20px_rgb(210_64_47/0.35)] hover:bg-red-600 disabled:opacity-60"
            >
              <Upload className="size-4" aria-hidden />
              Import
            </button>
          )}
        </div>
        {file && (
          <p className="mt-2 text-sm text-ink-2">
            {file.name} · {mb(file.size)}
          </p>
        )}
        {uploading && file && (
          <div className="mt-3">
            <p className="text-sm font-semibold">
              Sending… {mb(file.size * (sent ?? 0))} of {mb(file.size)}
            </p>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-grey-soft">
              <div className="h-full rounded-full bg-red" style={{ width: `${Math.round((sent ?? 0) * 100)}%` }} />
            </div>
            <p className="mt-1 text-xs text-muted">Keep this page open until it&apos;s sent. Big exports take a few minutes on mobile data.</p>
          </div>
        )}
        {error && <p className="mt-3 text-sm text-red">{error}</p>}
      </div>

      {imp && !uploading && (
        <div className="glass rounded-[var(--radius-card)] p-5">
          <Progress imp={imp} />
        </div>
      )}
    </div>
  );
}
