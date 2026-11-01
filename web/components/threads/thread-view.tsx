"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock, Pencil } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { SaveRows } from "@/components/saves/save-list";
import { threadsApi } from "@/lib/api";

/** One goal: its saves, newest first, and a name the person can change. */
export function ThreadView() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["thread", id],
    queryFn: () => threadsApi.get(id),
  });
  const rename = useMutation({
    mutationFn: (value: string) => threadsApi.rename(id, value),
    onSuccess: () => {
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["thread", id] });
      void queryClient.invalidateQueries({ queryKey: ["threads"] });
    },
  });

  if (isPending) return <p className="text-ink-2">Opening this goal…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;

  return (
    <article>
      <Link href="/threads" className="text-sm text-ink-2 hover:underline">
        ← Threads
      </Link>
      {editing ? (
        <form
          className="mt-2 flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (title.trim()) rename.mutate(title.trim());
          }}
        >
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={80}
            className="glass min-w-0 flex-1 rounded-full px-4 py-2 font-display text-lg font-bold"
            aria-label="Name this goal"
          />
          <button type="submit" disabled={rename.isPending} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
            Save
          </button>
          <button type="button" onClick={() => setEditing(false)} className="glass rounded-full px-4 py-2 text-sm font-semibold">
            Cancel
          </button>
          {rename.isError && <p className="w-full text-sm text-red">{rename.error.message}</p>}
        </form>
      ) : (
        <div className="mt-2 flex items-start gap-2">
          <h1 className="font-display text-2xl font-bold tracking-[-0.02em]">{data.title}</h1>
          <button
            type="button"
            onClick={() => {
              setTitle(data.title);
              setEditing(true);
            }}
            aria-label="Rename this goal"
            className="mt-1 rounded-full p-1.5 text-ink-2 hover:bg-glass-strong"
          >
            <Pencil className="size-4" />
          </button>
        </div>
      )}
      {data.summary && <p className="mt-1 text-ink-2">{data.summary}</p>}
      <p className="mt-1 flex items-center gap-1.5 text-sm text-muted">
        {data.saves} {data.saves === 1 ? "save" : "saves"}
        {data.locked && (
          <>
            {" · "}
            <Lock className="size-3.5" aria-hidden /> You named this, so Homing keeps the name.
          </>
        )}
      </p>
      <SaveRows saves={data.items} />
    </article>
  );
}
