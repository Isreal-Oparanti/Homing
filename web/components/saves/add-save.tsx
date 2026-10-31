"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { savesApi } from "@/lib/api";

/** Paste anything: a link, a note, a post. It opens the save card straight away. */
export function AddSave({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const save = useMutation({
    mutationFn: () => savesApi.create(text),
    onSuccess: (created) => {
      onClose();
      router.push(`/saves/${created.id}`);
    },
  });

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
        className="glass w-full max-w-lg rounded-[var(--radius-card)] p-5"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) save.mutate();
        }}
      >
        <h2 id="add-save-title" className="font-display text-lg font-bold tracking-[-0.02em]">
          Save something
        </h2>
        <p className="mt-1 text-sm text-ink-2">Paste a link, a post or a note.</p>
        <textarea
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          maxLength={20000}
          placeholder="https://… or anything you want to keep"
          className="mt-3 w-full resize-y rounded-xl border border-line bg-white/80 p-3 text-[15px] outline-none focus:border-ink/30"
        />
        {save.isError && <p className="mt-2 text-sm text-amber">{save.error.message}</p>}
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="glass rounded-full px-4 py-2 text-sm font-semibold">
            Cancel
          </button>
          <button
            type="submit"
            disabled={!text.trim() || save.isPending}
            className="rounded-full bg-red px-5 py-2 text-sm font-semibold text-white shadow-[0_6px_20px_rgb(210_64_47/0.35)] hover:bg-red-600 disabled:opacity-60"
          >
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </div>
  );
}
