"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageCircleQuestion, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SaveRows } from "@/components/saves/save-list";
import { askApi, searchApi } from "@/lib/api";

function useDebounced(value: string, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

/** Find a save as you type, or ask a question and get one answer page from your saves. */
export function SearchAsk() {
  const router = useRouter();
  const [text, setText] = useState("");
  const q = useDebounced(text.trim(), 300);
  const results = useQuery({
    queryKey: ["search", q],
    queryFn: () => searchApi.search(q),
    enabled: q.length >= 2,
  });
  const recent = useQuery({ queryKey: ["asks"], queryFn: () => askApi.recent() });
  const ask = useMutation({
    mutationFn: () => askApi.ask(text.trim()),
    onSuccess: (a) => router.push(`/ask/${a.id}`),
  });

  return (
    <div className="space-y-5">
      <form
        className="glass flex items-center gap-2 rounded-full py-1.5 pl-4 pr-1.5"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim().length >= 2) ask.mutate();
        }}
      >
        <Search className="size-4 shrink-0 text-muted" aria-hidden />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search, or ask a question about your saves"
          aria-label="Search or ask"
          className="min-w-0 flex-1 bg-transparent py-1.5 outline-none placeholder:text-muted"
        />
        <button
          type="submit"
          disabled={text.trim().length < 2 || ask.isPending}
          className="flex items-center gap-1.5 rounded-full bg-red px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          <MessageCircleQuestion className="size-4" aria-hidden />
          {ask.isPending ? "Asking…" : "Ask"}
        </button>
      </form>
      {ask.isError && <p className="text-sm text-red">{ask.error.message}</p>}

      {q.length >= 2 && (
        <section>
          {results.isPending && <p className="text-sm text-ink-2">Searching…</p>}
          {results.isError && <p className="text-sm text-ink-2">{results.error.message}</p>}
          {results.data && results.data.length === 0 && (
            <p className="text-sm text-ink-2">No saves match that. Try other words, or ask it as a question.</p>
          )}
          {results.data && results.data.length > 0 && (
            <>
              <p className="text-sm text-muted">Saves matching &ldquo;{q}&rdquo;, by words and by meaning.</p>
              <SaveRows saves={results.data} />
            </>
          )}
        </section>
      )}

      {q.length < 2 && recent.data && recent.data.length > 0 && (
        <section>
          <h2 className="font-display text-lg font-bold tracking-[-0.02em]">Questions you asked</h2>
          <ul className="mt-2 space-y-1.5">
            {recent.data.map((a) => (
              <li key={a.id}>
                <Link href={`/ask/${a.id}`} className="text-sm font-semibold text-ink-2 hover:underline">
                  {a.question}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
