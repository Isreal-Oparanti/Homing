"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { QuestionView } from "@/components/saves/question";
import { type Profile, type Question, profileApi } from "@/lib/api";
import { countryName } from "@/lib/countries";

const LEVEL: Record<string, string> = {
  fluent: "Fluent",
  working: "Working knowledge",
  basic: "Basic",
  none: "Not at all",
};
const LANGUAGE: Record<string, string> = { en: "English", fr: "French", ar: "Arabic", pt: "Portuguese", es: "Spanish" };
const STUDENT: Record<string, string> = {
  full_time: "Full-time student",
  part_time: "Part-time student",
  not_student: "Not a student",
};
const EDUCATION: Record<string, string> = {
  secondary: "Secondary school",
  undergraduate: "Undergraduate",
  postgraduate: "Postgraduate",
  graduate: "Graduated",
};

function choice(id: string, text: string, labels: Record<string, string>): Question {
  return { id, text, kind: "choice", options: Object.entries(labels).map(([value, label]) => ({ value, label })) };
}

type Row = { label: string; value: string | null; question: Question };

/** Every fact Homing can judge fit by: told ones show their answer, the rest "Not told yet". */
function rows(p: Profile): Row[] {
  const out: Row[] = [
    { label: "Lives in", value: p.residenceCountry ? countryName(p.residenceCountry) : null, question: { id: "residence_country", text: "Which country do you live in?", kind: "country" } },
    { label: "Citizen of", value: p.nationality[0] ? countryName(p.nationality[0]) : null, question: { id: "nationality", text: "Which country are you a citizen of?", kind: "country" } },
    { label: "Born in", value: p.birthYear ? String(p.birthYear) : null, question: { id: "birth_year", text: "What year were you born?", kind: "year" } },
    { label: "Studying", value: p.studentStatus ? (STUDENT[p.studentStatus] ?? p.studentStatus) : null, question: choice("student_status", "Are you a student right now?", STUDENT) },
    { label: "Level", value: p.educationLevel ? (EDUCATION[p.educationLevel] ?? p.educationLevel) : null, question: choice("education_level", "What level are you studying at, or have finished?", EDUCATION) },
    { label: "Company registered", value: p.companyRegistered === null ? null : p.companyRegistered ? "Yes" : "No", question: { id: "company_registered", text: "Is your company registered?", kind: "yesno" } },
  ];
  for (const [code, level] of Object.entries(p.languages)) {
    const name = LANGUAGE[code] ?? code.toUpperCase();
    out.push({ label: name, value: LEVEL[level] ?? level, question: choice(`language:${code}`, `How well do you speak ${name}?`, LEVEL) });
  }
  return out;
}

/** Everything Homing remembers about you, each one changeable or forgettable, and what it
 * doesn't know yet, answerable here so every opportunity and find is judged for you. */
export function ProfileView() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error } = useQuery({ queryKey: ["profile"], queryFn: () => profileApi.get() });
  const [editing, setEditing] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string | number | boolean | null }) => profileApi.set(id, value),
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
      setEditing(null);
      for (const key of [["save"], ["today"], ["saves"], ["finds"]]) void queryClient.invalidateQueries({ queryKey: key });
    },
  });

  if (isPending) return <p className="text-ink-2">Loading…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  const list = rows(data);
  const missing = list.filter((r) => r.value === null).length;
  return (
    <div className="glass rounded-[var(--radius-card)] p-5">
      {missing > 0 && (
        <p className="text-sm text-ink-2">
          Tell Homing what it doesn&apos;t know yet, and every opportunity you save, and every one it finds for you, is
          judged against it. Or skip: a card asks when it needs to.
        </p>
      )}
      <ul className="divide-y divide-line">
        {list.map((row) => (
          <li key={row.question.id} className="py-3">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted">{row.label}</p>
                <p className={row.value === null ? "text-ink-2" : "font-semibold"}>{row.value ?? "Not told yet"}</p>
              </div>
              <button
                type="button"
                onClick={() => setEditing(editing === row.question.id ? null : row.question.id)}
                className="text-sm text-ink-2 underline"
              >
                {editing === row.question.id ? "Cancel" : row.value === null ? "Tell Homing" : "Change"}
              </button>
              {row.value !== null && (
                <button
                  type="button"
                  disabled={change.isPending}
                  onClick={() => change.mutate({ id: row.question.id, value: null })}
                  className="text-sm text-ink-2 underline"
                >
                  Forget
                </button>
              )}
            </div>
            {editing === row.question.id && (
              <div className="mt-3">
                <QuestionView question={row.question} busy={change.isPending} onAnswer={(value) => change.mutate({ id: row.question.id, value })} />
              </div>
            )}
          </li>
        ))}
      </ul>
      {change.isError && <p className="mt-2 text-sm text-amber">{change.error.message}</p>}
      <p className="mt-3 text-xs text-muted">
        Used only to check whether opportunities fit you, by code on our server. Never sent to an AI model.
      </p>
    </div>
  );
}
