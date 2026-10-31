"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import Link from "next/link";

import { type SaveListItem, savesApi } from "@/lib/api";

function label(save: SaveListItem) {
  if (save.visibility === "private") return "Private save";
  return save.title ?? save.label ?? save.url ?? save.text?.slice(0, 80) ?? "Your save";
}

function line(save: SaveListItem) {
  if (save.visibility === "private") return "Kept private. We never send these to AI.";
  if (save.what) return save.what;
  if (save.status === "failed") return save.error ?? "Couldn't read this save.";
  return save.error ?? "Reading it…";
}

/** Every save, newest first. Until threads exist, this is how you find a save again. */
export function SaveList() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["saves"],
    queryFn: () => savesApi.list(),
  });

  if (isPending) return <p className="text-ink-2">Loading your saves…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  if (data.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="font-display text-lg font-bold tracking-[-0.02em]">Your saves</h2>
      <p className="text-sm text-ink-2">Not grouped into threads yet.</p>
      <ul className="mt-3 space-y-2">
        {data.map((save) => (
          <li key={save.id}>
            <Link
              href={`/saves/${save.id}`}
              className="glass block rounded-[var(--radius-card)] px-4 py-3 hover:bg-glass-strong"
            >
              <p className="flex items-center gap-1.5 truncate font-semibold">
                {save.visibility === "private" && <Lock className="size-3.5 shrink-0" aria-hidden />}
                <span className="truncate">{label(save)}</span>
              </p>
              <p className="mt-0.5 line-clamp-2 text-sm text-ink-2">{line(save)}</p>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
