"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { QuestionView } from "@/components/saves/question";
import { EmptyState } from "@/components/shell/empty-state";
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

type Row = { label: string; value: string; question: Question };

function rows(p: Profile): Row[] {
  const out: Row[] = [];
  if (p.birthYear) out.push({ label: "Born in", value: String(p.birthYear), question: { id: "birth_year", text: "What year were you born?", kind: "year" } });
  if (p.nationality[0]) out.push({ label: "Citizen of", value: countryName(p.nationality[0]), question: { id: "nationality", text: "Which country are you a citizen of?", kind: "country" } });
  if (p.residenceCountry) out.push({ label: "Lives in", value: countryName(p.residenceCountry), question: { id: "residence_country", text: "Which country do you live in?", kind: "country" } });
  if (p.studentStatus) out.push({ label: "Studying", value: STUDENT[p.studentStatus] ?? p.studentStatus, question: choice("student_status", "Are you a student right now?", STUDENT) });
  if (p.educationLevel) out.push({ label: "Level", value: EDUCATION[p.educationLevel] ?? p.educationLevel, question: choice("education_level", "What level are you studying at, or have finished?", EDUCATION) });
  for (const [code, level] of Object.entries(p.languages)) {
    const name = LANGUAGE[code] ?? code.toUpperCase();
    out.push({ label: name, value: LEVEL[level] ?? level, question: choice(`language:${code}`, `How well do you speak ${name}?`, LEVEL) });
  }
  if (p.companyRegistered !== null) out.push({ label: "Company registered", value: p.companyRegistered ? "Yes" : "No", question: { id: "company_registered", text: "Is your company registered?", kind: "yesno" } });
  return out;
}

/** Everything Homing remembers from your answers, each one changeable or forgettable. */
export function ProfileView() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error } = useQuery({ queryKey: ["profile"], queryFn: () => profileApi.get() });
  const [editing, setEditing] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string | number | boolean | null }) => profileApi.set(id, value),
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
      setEditing(null);
      for (const key of [["save"], ["today"], ["saves"]]) void queryClient.invalidateQueries({ queryKey: key });
    },
  });

  if (isPending) return <p className="text-ink-2">Loading…</p>;
  if (isError) return <p className="text-ink-2">{error.message}</p>;
  const list = rows(data);
  if (list.length === 0) {
    return (
      <EmptyState
        title="Nothing yet."
        body="When an opportunity needs to know something about you, its card asks once. Your answers show up here."
      />
    );
  }
  return (
    <div className="glass rounded-[var(--radius-card)] p-5">
      <ul className="divide-y divide-line">
        {list.map((row) => (
          <li key={row.question.id} className="py-3">
            <div className="flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-xs text-muted">{row.label}</p>
                <p className="font-semibold">{row.value}</p>
              </div>
              <button type="button" onClick={() => setEditing(editing === row.question.id ? null : row.question.id)} className="text-sm text-ink-2 underline">
                {editing === row.question.id ? "Cancel" : "Change"}
              </button>
              <button type="button" disabled={change.isPending} onClick={() => change.mutate({ id: row.question.id, value: null })} className="text-sm text-ink-2 underline">
                Forget
              </button>
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
