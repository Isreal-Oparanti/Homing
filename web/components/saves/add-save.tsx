"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileText, ImageIcon, MessageCircle, Paperclip, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { savesApi } from "@/lib/api";

const MAX_FILES = 6;
const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/png,image/jpeg,image/webp,image/gif,application/pdf";

/** Why these files can't be saved together, or null if they can. */
function problem(files: File[]): string | null {
  if (files.length > MAX_FILES) return `Add up to ${MAX_FILES} files at a time.`;
  if (files.some((f) => f.size > MAX_BYTES)) return "Files must be 10 MB or smaller.";
  if (files.some((f) => f.type === "application/pdf") && files.length > 1) return "Add a PDF on its own.";
  // Some phones send no type at all; the server checks the real type from the bytes.
  if (files.some((f) => f.type && !ACCEPT.split(",").includes(f.type))) {
    return "Homing can read images and PDFs for now.";
  }
  return null;
}

/** Paste anything: a link, a post, a note, screenshots, a flyer or a PDF. */
export function AddSave({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const picker = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const issue = problem(files);

  const save = useMutation({
    mutationFn: () => (files.length ? savesApi.upload(files, text) : savesApi.create(text)),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ["saves"] });
      onClose();
      router.push(`/saves/${created.id}`);
    },
  });

  function add(list: FileList | File[] | null) {
    if (list && list.length) setFiles((current) => [...current, ...Array.from(list)]);
  }

  const ready = (files.length > 0 && !issue) || (!files.length && text.trim().length > 0);

  return (
    <div
      className="fixed inset-0 z-20 flex items-end justify-center bg-ink/20 p-4 backdrop-blur-sm sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-save-title"
      onClick={onClose}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
    >
      <form
        className={`glass w-full max-w-lg rounded-[var(--radius-card)] p-5 ${dragging ? "ring-2 ring-red" : ""}`}
        onClick={(e) => e.stopPropagation()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          add(e.dataTransfer.files);
        }}
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) save.mutate();
        }}
      >
        <h2 id="add-save-title" className="font-display text-lg font-bold tracking-[-0.02em]">
          Save something
        </h2>
        <p className="mt-1 text-sm text-ink-2">Paste a link, a post or a note, or add screenshots, a flyer or a PDF.</p>
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={(e) => {
            if (e.clipboardData.files.length) {
              e.preventDefault();
              add(e.clipboardData.files);
            }
          }}
          rows={files.length ? 2 : 5}
          maxLength={20000}
          placeholder={files.length ? "Add a note (optional)" : "https://… or anything you want to keep"}
          className="mt-3 w-full resize-y rounded-xl border border-line bg-white/80 p-3 text-[15px] outline-none focus:border-ink/30"
        />

        {files.length > 0 && (
          <ul className="mt-2 space-y-1.5">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="flex items-center gap-2 rounded-xl bg-white/70 px-3 py-1.5 text-sm">
                {f.type === "application/pdf" ? (
                  <FileText className="size-4 shrink-0 text-ink-2" aria-hidden />
                ) : (
                  <ImageIcon className="size-4 shrink-0 text-ink-2" aria-hidden />
                )}
                <span className="min-w-0 flex-1 truncate">{f.name || "Pasted image"}</span>
                <span className="text-xs text-muted">{Math.max(1, Math.round(f.size / 1024))} KB</span>
                <button
                  type="button"
                  aria-label={`Remove ${f.name || "this file"}`}
                  onClick={() => setFiles((current) => current.filter((_, j) => j !== i))}
                  className="rounded-full p-0.5 text-ink-2 hover:bg-grey-soft"
                >
                  <X className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {issue && <p className="mt-2 text-sm text-amber">{issue}</p>}
        {save.isError && <p className="mt-2 text-sm text-amber">{save.error.message}</p>}

        <div className="mt-3 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={() => picker.current?.click()}
            className="flex items-center gap-1.5 rounded-full px-3 py-2 text-sm font-semibold text-ink-2 hover:bg-white/60"
          >
            <Paperclip className="size-4" aria-hidden />
            Add screenshots, a flyer or a PDF
          </button>
          <input
            ref={picker}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => {
              add(e.target.files);
              e.target.value = "";
            }}
          />
          <div className="flex gap-2">
            <button type="button" onClick={onClose} className="glass rounded-full px-4 py-2 text-sm font-semibold">
              Cancel
            </button>
            <button
              type="submit"
              disabled={!ready || save.isPending}
              className="rounded-full bg-red px-5 py-2 text-sm font-semibold text-white shadow-[0_6px_20px_rgb(210_64_47/0.35)] hover:bg-red-600 disabled:opacity-60"
            >
              {save.isPending ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
        <Link
          href="/import"
          onClick={onClose}
          className="mt-3 flex items-center gap-1.5 px-3 text-sm font-semibold text-ink-2 hover:underline"
        >
          <MessageCircle className="size-4" aria-hidden />
          Or import a whole WhatsApp chat
        </Link>
      </form>
    </div>
  );
}
