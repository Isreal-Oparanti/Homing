"use client";

import { useState } from "react";

import type { Question } from "@/lib/api";
import { COUNTRIES } from "@/lib/countries";

const BUTTON =
  "rounded-full border border-line bg-white/80 px-3.5 py-1.5 text-sm font-semibold hover:border-ink/30 disabled:opacity-50";

/** One question, answered with a tap where possible. */
export function QuestionView({
  question,
  busy,
  onAnswer,
}: {
  question: Question;
  busy: boolean;
  onAnswer: (value: string | number | boolean) => void;
}) {
  const [typed, setTyped] = useState("");

  return (
    <div>
      <p className="font-semibold">{question.text}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {question.kind === "choice" &&
          question.options?.map((o) => (
            <button key={o.value} type="button" disabled={busy} onClick={() => onAnswer(o.value)} className={BUTTON}>
              {o.label}
            </button>
          ))}
        {question.kind === "yesno" && (
          <>
            <button type="button" disabled={busy} onClick={() => onAnswer(true)} className={BUTTON}>
              Yes
            </button>
            <button type="button" disabled={busy} onClick={() => onAnswer(false)} className={BUTTON}>
              No
            </button>
          </>
        )}
        {(question.kind === "year" || question.kind === "country") && (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (typed) onAnswer(question.kind === "year" ? Number(typed) : typed);
            }}
          >
            {question.kind === "year" ? (
              <input
                inputMode="numeric"
                pattern="[0-9]{4}"
                maxLength={4}
                placeholder="e.g. 2001"
                value={typed}
                onChange={(e) => setTyped(e.target.value.replace(/\D/g, ""))}
                className="w-28 rounded-full border border-line bg-white/80 px-3.5 py-1.5 text-sm outline-none focus:border-ink/30"
                aria-label={question.text}
              />
            ) : (
              <select
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                className="rounded-full border border-line bg-white/80 px-3 py-1.5 text-sm outline-none"
                aria-label={question.text}
              >
                <option value="">Choose a country</option>
                {COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
            <button type="submit" disabled={busy || !typed} className={BUTTON}>
              Save
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
