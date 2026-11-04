/**
 * Typed client for the Homing API, called through the /api/backend proxy.
 * The API speaks snake_case; the web app uses camelCase. Map at this boundary only.
 */

export class HomingApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = body?.error;
    throw new HomingApiError(
      res.status,
      err?.code ?? "error",
      err?.message ?? "Something went wrong. Try again.",
    );
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

async function uploadTicket(): Promise<{ url: string; api: string; ticket: string }> {
  const res = await fetch("/api/upload-ticket", { method: "POST" });
  if (!res.ok) {
    const err = (await res.json().catch(() => null))?.error;
    throw new HomingApiError(res.status, err?.code ?? "error", err?.message ?? "Please sign in again.");
  }
  return res.json();
}

export type Agent = "what" | "true" | "for" | "when" | "system";

export type Evidence = {
  label: string;
  url?: string;
  snapshotId?: string;
  quote?: string;
};

export type AgentEvent = {
  id: number;
  agent: Agent;
  action: string;
  summary: string;
  saveId: string | null;
  threadId: string | null;
  cardId: string | null;
  evidence: Evidence[];
  /** The Meta models behind this step: [] means code did it; null, from before we kept it. */
  models: string[] | null;
  createdAt: string;
};

type RawEvidence = { label: string; url?: string; snapshot_id?: string; quote?: string };

type RawAgentEvent = {
  id: number;
  agent: Agent;
  action: string;
  summary: string;
  save_id: string | null;
  thread_id: string | null;
  card_id: string | null;
  evidence: RawEvidence[];
  models?: string[] | null;
  created_at: string;
};

export function toAgentEvent(raw: RawAgentEvent): AgentEvent {
  return {
    id: raw.id,
    agent: raw.agent,
    action: raw.action,
    summary: raw.summary,
    saveId: raw.save_id,
    threadId: raw.thread_id,
    cardId: raw.card_id,
    evidence: raw.evidence.map((e) => ({
      label: e.label,
      url: e.url,
      snapshotId: e.snapshot_id,
      quote: e.quote,
    })),
    models: raw.models ?? null,
    createdAt: raw.created_at,
  };
}

export type TeamPage = { items: AgentEvent[]; nextCursor: string | null };

/** What's happening now: each agent's jobs in hand, and the saves waiting on you. */
export type Attention = {
  working: Record<string, number>;
  needsYou: number;
  needsYouItems: { saveId: string; title: string }[];
};

type RawAttention = {
  working: Record<string, number>;
  needs_you: number;
  needs_you_items: { save_id: string; title: string }[];
};

function toAttention(a: RawAttention): Attention {
  return {
    working: a.working,
    needsYou: a.needs_you,
    needsYouItems: a.needs_you_items.map((i) => ({ saveId: i.save_id, title: i.title })),
  };
}

/** One Meta model's real calls for this person. */
export type ModelUse = { model: string; callsToday: number; calls: number; tokens: number };

export type TeamOverview = {
  now: Attention;
  models: ModelUse[];
  saves: number;
  goals: { id: string; title: string; saves: number }[];
  goalOf: Record<string, string>;
  date: string;
  hours: Record<string, number[]>;
  hourNow: number;
};

export const teamApi = {
  async list(cursor?: string): Promise<TeamPage> {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
    const page = await api<{ items: RawAgentEvent[]; next_cursor: string | null }>(
      `team${query}`,
    );
    return { items: page.items.map(toAgentEvent), nextCursor: page.next_cursor };
  },
  /** For the menu's badge: what's waiting on you, and whether agents are at work. */
  async attention(): Promise<Attention> {
    return toAttention(await api<RawAttention>("team/attention"));
  },
  /** What the agents map and today's clock draw: real counts only. */
  async overview(): Promise<TeamOverview> {
    const raw = await api<{
      saves: number;
      goals: { id: string; title: string; saves: number }[];
      goal_of: Record<string, string>;
      date: string;
      hours: Record<string, number[]>;
      hour_now: number;
      now: RawAttention;
      models?: { model: string; calls_today: number; calls: number; tokens: number }[];
    }>("team/overview");
    return {
      models: (raw.models ?? []).map((m) => ({
        model: m.model,
        callsToday: m.calls_today,
        calls: m.calls,
        tokens: m.tokens,
      })),
      now: toAttention(raw.now),
      saves: raw.saves,
      goals: raw.goals,
      goalOf: raw.goal_of,
      date: raw.date,
      hours: raw.hours,
      hourNow: raw.hour_now,
    };
  },
  /** Local development only: queues a system.echo job to test the live feed. */
  echo(message: string) {
    return api<{ job_id: number }>("dev/echo", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },
};

export const meApi = {
  get: () => api<{ id: string; email: string; name: string | null }>("me"),
  /** The private calendar feed: every date and moment, in the person's own calendar. */
  async calendar(): Promise<{ httpsUrl: string; webcalUrl: string; googleUrl: string }> {
    const raw = await api<{ https_url: string; webcal_url: string; google_url: string }>(
      "me/calendar",
    );
    return { httpsUrl: raw.https_url, webcalUrl: raw.webcal_url, googleUrl: raw.google_url };
  },
};

export type SaveSummary = {
  id: string;
  kind: "note" | "link" | "list" | "image" | "voice" | "video" | "pdf" | "file";
  platform: string | null;
  url: string | null;
  label: string | null;
  text: string | null;
  savedAt: string;
  status: "received" | "reading" | "ready" | "failed";
  visibility: "normal" | "private";
  error: string | null;
  /** Images or a PDF on the save, shown from /api/backend/saves/{id}/files/{n}. */
  files: number;
};

export type Reading = {
  title: string;
  what: string;
  keyFacts: {
    dates?: { text: string; role: string }[];
    amounts?: { text: string }[];
    requirements?: { text: string }[];
    organisations?: string[];
    places?: string[];
  };
  isCheckable: boolean;
  isOpportunity: boolean;
};

export type Answer = "what" | "true" | "for" | "when";

/** Our copy of the content, kept at save time. */
export type Copy = {
  id: string;
  kind: "page_text" | "post_text" | "transcript" | "metadata" | string;
  sourceUrl: string | null;
  chars: number;
  excerpt: string;
};

/** Is it true?: only findings code has verified against the official page reach the web. */
export type TrueAnswer = {
  verdict:
    | "fits_you"
    | "closed"
    | "not_for_you"
    | "needs_your_answer"
    | "couldnt_confirm"
    | "nothing_to_check"
    /** An imported opportunity that looked closed or old, so Is it true? held off. */
    | "not_checked"
    | "checked";
  officialUrl: string | null;
  /** The save is just a link to the official page itself. */
  samePage: boolean;
  /** No official page: the rules quote the post itself and aren't confirmed. */
  fromPost: boolean;
  note: string | null;
  deadline: { at: string; display: string; tzStated: boolean; sourceText: string | null } | null;
  findings: { point: string; quote: string; kind: "left_out" | "differs" | "confirmed" | "closed" }[];
  rules: EligibilityRule[];
  questions: Question[];
  /** For a save that lists several opportunities: each one, checked on its own page. */
  items: CheckedItem[];
  question: string | null;
};

export type CheckedItem = {
  name: string;
  url: string | null;
  status: "queued" | "done";
  verdict: TrueAnswer["verdict"] | null;
  /** What the post said about this item. */
  note: string | null;
  /** Why it couldn't be checked, e.g. "We couldn't open triple-funds.com." */
  problem: string | null;
  officialUrl: string | null;
  /** "search" when the save had no link and Homing found the site itself. */
  foundBy: string | null;
  findings: TrueAnswer["findings"];
  rules: EligibilityRule[];
  deadline: { at: string; display: string } | null;
  closed: string | null;
};

export type EligibilityRule = {
  rule: string;
  plain: string;
  quote: string;
  strength: "required" | "preferred";
  result: "meets" | "fails" | "unknown";
};

/** One thing Homing needs to know to judge an opportunity. Asked on the card, remembered. */
export type Question = {
  id: string;
  text: string;
  kind: "choice" | "yesno" | "year" | "country";
  options?: { value: string; label: string }[];
};

/** What Homing remembers from your answers. */
export type Profile = {
  birthYear: number | null;
  nationality: string[];
  residenceCountry: string | null;
  studentStatus: string | null;
  educationLevel: string | null;
  languages: Record<string, string>;
  companyRegistered: boolean | null;
};

export type ForAnswer = {
  threads: { id: string; title: string; position: number; count: number }[];
  duplicateOf: string | null;
};

export type WhenAnswer = {
  kind: "date" | "moment" | "none";
  source: "check" | "reading" | "thread" | "user";
  dueAt: string | null;
  display: string | null;
  bringBackAt: string | null;
  explanation: string;
  sourceText: string | null;
  tzStated: boolean;
  timeStated: boolean;
};

export type SaveCard = {
  save: SaveSummary;
  what: Reading | null;
  true: TrueAnswer | null;
  for: ForAnswer | null;
  when: WhenAnswer | null;
  copies: Copy[];
  pending: Answer[];
  /** What produced each answer: the Meta models (none: code did it), and how. */
  by: Partial<Record<Answer, { models: string[]; how: string }>>;
};

export type TodayCard = {
  id: string;
  /** deadline: a save due back; prep: a moment you typed is coming. */
  kind: "deadline" | "prep";
  saveId: string | null;
  threadIds: string[];
  title: string;
  whyNow: string;
  nextStep: string;
  dueAt: string | null;
  tzStated: boolean;
  unconfirmed: boolean;
};

/** A save already set to come back, and the date it's for. */
export type ComingBack = { saveId: string; title: string; backOn: string; due: string };

/** Something coming up, in your words; When will you need it? finds the goals it needs. */
export type Moment = {
  id: string;
  text: string;
  at: string;
  display: string;
  threads: { id: string; title: string }[];
};

/** A row in the saves list: the save plus its reading's title, when there is one. */
export type SaveListItem = SaveSummary & { title: string | null; what: string | null };

type RawSave = {
  id: string;
  kind: SaveSummary["kind"];
  platform: string | null;
  url: string | null;
  label: string | null;
  text: string | null;
  saved_at: string;
  status: SaveSummary["status"];
  visibility: SaveSummary["visibility"];
  error: string | null;
  files?: number;
};

type RawTrue = {
  verdict: TrueAnswer["verdict"];
  official_url?: string | null;
  same_page?: boolean;
  from_post?: boolean;
  note?: string | null;
  deadline?: { at: string; display: string; tz_stated: boolean; source_text: string | null } | null;
  findings?: TrueAnswer["findings"];
  rules?: EligibilityRule[];
  questions?: Question[];
  items?: {
    name: string;
    url: string | null;
    status: CheckedItem["status"];
    verdict: CheckedItem["verdict"];
    note: string | null;
    problem?: string | null;
    official_url: string | null;
    found_by?: string | null;
    findings: TrueAnswer["findings"];
    rules: EligibilityRule[];
    deadline: { at: string; display: string } | null;
    closed: string | null;
  }[];
  question?: string | null;
};

type RawWhen = {
  kind: WhenAnswer["kind"];
  source: WhenAnswer["source"];
  due_at: string | null;
  display: string | null;
  bring_back_at: string | null;
  explanation: string;
  source_text: string | null;
  tz_stated: boolean;
  time_stated: boolean;
};

function toTrue(raw: RawTrue | null): TrueAnswer | null {
  if (!raw) return null;
  return {
    verdict: raw.verdict,
    officialUrl: raw.official_url ?? null,
    samePage: raw.same_page ?? false,
    fromPost: raw.from_post ?? false,
    note: raw.note ?? null,
    deadline: raw.deadline
      ? {
          at: raw.deadline.at,
          display: raw.deadline.display,
          tzStated: raw.deadline.tz_stated,
          sourceText: raw.deadline.source_text,
        }
      : null,
    findings: raw.findings ?? [],
    rules: raw.rules ?? [],
    questions: raw.questions ?? [],
    items: (raw.items ?? []).map((i) => ({
      name: i.name,
      url: i.url,
      status: i.status,
      verdict: i.verdict,
      note: i.note,
      problem: i.problem ?? null,
      officialUrl: i.official_url,
      foundBy: i.found_by ?? null,
      findings: i.findings ?? [],
      rules: i.rules ?? [],
      deadline: i.deadline,
      closed: i.closed,
    })),
    question: raw.question ?? null,
  };
}

function toWhen(raw: RawWhen | null): WhenAnswer | null {
  if (!raw) return null;
  return {
    kind: raw.kind,
    source: raw.source,
    dueAt: raw.due_at,
    display: raw.display,
    bringBackAt: raw.bring_back_at,
    explanation: raw.explanation,
    sourceText: raw.source_text,
    tzStated: raw.tz_stated,
    timeStated: raw.time_stated,
  };
}

type RawCopy = { id: string; kind: string; source_url: string | null; chars: number; excerpt: string };

type RawReading = {
  title: string;
  what: string;
  key_facts: Reading["keyFacts"];
  is_checkable: boolean;
  is_opportunity: boolean;
};

function toSave(raw: RawSave): SaveSummary {
  return {
    id: raw.id,
    kind: raw.kind,
    platform: raw.platform,
    url: raw.url,
    label: raw.label,
    text: raw.text,
    savedAt: raw.saved_at,
    status: raw.status,
    visibility: raw.visibility,
    error: raw.error,
    files: raw.files ?? 0,
  };
}

export const savesApi = {
  async create(text: string): Promise<SaveSummary> {
    return toSave(await api<RawSave>("saves", { method: "POST", body: JSON.stringify({ text }) }));
  },
  async list(): Promise<SaveListItem[]> {
    const page = await api<{ items: (RawSave & { title: string | null; what: string | null })[] }>(
      "saves?limit=50",
    );
    return page.items.map((raw) => ({ ...toSave(raw), title: raw.title, what: raw.what }));
  },
  /** Screenshots, a flyer or a PDF (several images become one save). */
  async upload(files: File[], note: string): Promise<SaveSummary> {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    if (note.trim()) form.append("note", note.trim());
    // Files go straight to the API with a short-lived ticket, because the web server caps
    // request bodies at 4.5 MB. No content type: the browser sets the multipart boundary.
    const { url, ticket } = await uploadTicket();
    const res = await fetch(url, {
      method: "POST",
      body: form,
      headers: { Authorization: `Bearer ${ticket}` },
    }).catch(() => {
      throw new HomingApiError(503, "unreachable", "Homing's server isn't reachable right now.");
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new HomingApiError(
        res.status,
        body?.error?.code ?? "error",
        body?.error?.message ?? "Couldn't save that file. Try again.",
      );
    }
    return toSave(await res.json());
  },
  /** Answer one question; every saved opportunity is re-judged. Returns what changed. */
  async answer(id: string, questionId: string, value: string | number | boolean): Promise<string> {
    const raw = await api<{ summary: string }>(`saves/${encodeURIComponent(id)}/answer`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId, value }),
    });
    return raw.summary;
  },
  /** Check a save Is it true? held off on. */
  async checkNow(id: string): Promise<void> {
    await api(`saves/${encodeURIComponent(id)}/check`, { method: "POST" });
  },
  /** A YouTube transcript the person copied from "Show transcript"; the save is read again. */
  async pasteTranscript(id: string, text: string): Promise<{ lines: number }> {
    return api<{ lines: number }>(`saves/${encodeURIComponent(id)}/transcript`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },
  /** A page's text, pasted by the person when Homing couldn't read the link itself. */
  async pastePageText(id: string, text: string): Promise<{ chars: number }> {
    return api<{ chars: number }>(`saves/${encodeURIComponent(id)}/text`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  },
  /** The owner's own text of a private save, fetched only when they tap Show. */
  async reveal(id: string): Promise<string> {
    const raw = await api<{ text: string }>(`saves/${encodeURIComponent(id)}/reveal`, {
      cache: "no-store",
    });
    return raw.text;
  },
  async get(id: string): Promise<SaveCard> {
    const raw = await api<{
      save: RawSave;
      what: RawReading | null;
      true: RawTrue | null;
      for: { threads: ForAnswer["threads"]; duplicate_of: string | null } | null;
      when: RawWhen | null;
      copies: RawCopy[];
      pending: Answer[];
      by?: SaveCard["by"];
    }>(`saves/${encodeURIComponent(id)}`);
    return {
      save: toSave(raw.save),
      what: raw.what && {
        title: raw.what.title,
        what: raw.what.what,
        keyFacts: raw.what.key_facts ?? {},
        isCheckable: raw.what.is_checkable,
        isOpportunity: raw.what.is_opportunity,
      },
      true: toTrue(raw.true),
      for: raw.for && { threads: raw.for.threads, duplicateOf: raw.for.duplicate_of },
      when: toWhen(raw.when),
      copies: raw.copies.map((c) => ({
        id: c.id,
        kind: c.kind,
        sourceUrl: c.source_url,
        chars: c.chars,
        excerpt: c.excerpt,
      })),
      pending: raw.pending,
      by: raw.by ?? {},
    };
  },
};

type RawCard = {
  id: string;
  kind: TodayCard["kind"];
  save_id: string | null;
  thread_ids: string[];
  title: string;
  why_now: string;
  next_step: string;
  due_at: string | null;
  tz_stated: boolean;
  unconfirmed: boolean;
};

function toCard(c: RawCard): TodayCard {
  return {
    id: c.id,
    kind: c.kind,
    saveId: c.save_id,
    threadIds: c.thread_ids,
    title: c.title,
    whyNow: c.why_now,
    nextStep: c.next_step,
    dueAt: c.due_at,
    tzStated: c.tz_stated,
    unconfirmed: c.unconfirmed,
  };
}

/** A line on a prep sheet, with the video seconds that back it. */
export type SheetItem = { text: string; cites: { video: string; t: number }[] };
export type SheetVideo = {
  saveId: string;
  title: string;
  url: string;
  thread: string | null;
  points: { tStart: number; tEnd: number; point: string; quote: string }[];
};
export type PrepSheet = {
  status: "queued" | "working" | "ready" | "failed";
  agree: SheetItem[];
  disagree: { topic: string; sides: SheetItem[] }[];
  checklist: SheetItem[];
  videos: Record<string, SheetVideo>;
  reel: { video: string; start: number; end: number }[];
  watched: number;
  droppedPoints: number;
  skipped: { noCaptions: number; reels: number; others: number };
};

type RawSheet = {
  status: PrepSheet["status"];
  agree?: SheetItem[];
  disagree?: PrepSheet["disagree"];
  checklist?: SheetItem[];
  videos?: Record<
    string,
    {
      save_id: string;
      title: string;
      url: string;
      thread: string | null;
      points: { t_start: number; t_end: number; point: string; quote: string }[];
    }
  >;
  reel?: PrepSheet["reel"];
  watched?: number;
  dropped_points?: number;
  skipped?: { no_captions: number; reels: number; others: number };
};

function toSheet(s: RawSheet): PrepSheet {
  return {
    status: s.status,
    agree: s.agree ?? [],
    disagree: s.disagree ?? [],
    checklist: s.checklist ?? [],
    videos: Object.fromEntries(
      Object.entries(s.videos ?? {}).map(([id, v]) => [
        id,
        {
          saveId: v.save_id,
          title: v.title,
          url: v.url,
          thread: v.thread,
          points: v.points.map((p) => ({
            tStart: p.t_start,
            tEnd: p.t_end,
            point: p.point,
            quote: p.quote,
          })),
        },
      ]),
    ),
    reel: s.reel ?? [],
    watched: s.watched ?? 0,
    droppedPoints: s.dropped_points ?? 0,
    skipped: {
      noCaptions: s.skipped?.no_captions ?? 0,
      reels: s.skipped?.reels ?? 0,
      others: s.skipped?.others ?? 0,
    },
  };
}

export const todayApi = {
  async get(): Promise<{
    date: string;
    cards: TodayCard[];
    moments: Moment[];
    comingBack: ComingBack[];
  }> {
    const raw = await api<{
      date: string;
      cards: RawCard[];
      moments: Moment[];
      coming_back: { save_id: string; title: string; back_on: string; due: string }[];
    }>("today");
    return {
      date: raw.date,
      cards: raw.cards.map(toCard),
      moments: raw.moments,
      comingBack: raw.coming_back.map((c) => ({
        saveId: c.save_id,
        title: c.title,
        backOn: c.back_on,
        due: c.due,
      })),
    };
  },
  /** use: done with it; dismiss: never again; later: back tomorrow morning. */
  async act(cardId: string, action: "use" | "dismiss" | "later"): Promise<void> {
    await api(`cards/${encodeURIComponent(cardId)}/act`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
  },
  /** One card; a prep card comes with its sheet (made by a job, so it may still be working). */
  async card(cardId: string): Promise<TodayCard & { sheet: PrepSheet | null }> {
    const raw = await api<RawCard & { sheet: RawSheet | null }>(
      `cards/${encodeURIComponent(cardId)}`,
    );
    return { ...toCard(raw), sheet: raw.sheet ? toSheet(raw.sheet) : null };
  },
  async addMoment(text: string): Promise<Moment> {
    return api<Moment>("moments", { method: "POST", body: JSON.stringify({ text }) });
  },
  async removeMoment(id: string): Promise<void> {
    await api(`moments/${encodeURIComponent(id)}`, { method: "DELETE" });
  },
};

type RawProfile = {
  birth_year: number | null;
  nationality: string[];
  residence_country: string | null;
  student_status: string | null;
  education_level: string | null;
  languages: Record<string, string>;
  company_registered: boolean | null;
};

function toProfile(raw: RawProfile): Profile {
  return {
    birthYear: raw.birth_year,
    nationality: raw.nationality,
    residenceCountry: raw.residence_country,
    studentStatus: raw.student_status,
    educationLevel: raw.education_level,
    languages: raw.languages,
    companyRegistered: raw.company_registered,
  };
}

export const profileApi = {
  async get(): Promise<Profile> {
    return toProfile(await api<RawProfile>("me/profile"));
  },
  /** Change one remembered answer, or forget it with null. */
  async set(questionId: string, value: string | number | boolean | null): Promise<Profile> {
    return toProfile(
      await api<RawProfile>("me/profile", {
        method: "PUT",
        body: JSON.stringify({ question_id: questionId, value }),
      }),
    );
  },
};

/** A WhatsApp export on its way in (server/app/api/v1/imports.py). */
export type ImportCounts = {
  messages?: number;
  saves?: number;
  media?: number;
  private?: number;
  duplicates?: number;
  skipped?: number;
  already?: number;
  total?: number;
  done?: number;
};

export type ImportStatus = {
  id: string;
  status: "received" | "importing" | "done" | "failed";
  counts: ImportCounts;
  error: string | null;
  createdAt: string;
  finishedAt: string | null;
};

type RawImport = {
  id: string;
  status: ImportStatus["status"];
  counts: ImportCounts;
  error: string | null;
  created_at: string;
  finished_at: string | null;
};

function toImport(raw: RawImport): ImportStatus {
  return {
    id: raw.id,
    status: raw.status,
    counts: raw.counts ?? {},
    error: raw.error,
    createdAt: raw.created_at,
    finishedAt: raw.finished_at,
  };
}

export const importApi = {
  /**
   * Sends the export straight to the API with an upload ticket (it can be hundreds of MB, far
   * over the web server's 4.5 MB limit). XHR, not fetch, because only XHR reports progress.
   */
  async upload(file: File, onProgress: (fraction: number) => void): Promise<ImportStatus> {
    const { api, ticket } = await uploadTicket();
    const form = new FormData();
    form.append("file", file);
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${api}/imports/whatsapp`);
      xhr.setRequestHeader("Authorization", `Bearer ${ticket}`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded / e.total);
      };
      xhr.onload = () => {
        const body = (() => {
          try {
            return JSON.parse(xhr.responseText);
          } catch {
            return null;
          }
        })();
        if (xhr.status >= 200 && xhr.status < 300 && body) resolve(toImport(body));
        else
          reject(
            new HomingApiError(
              xhr.status,
              body?.error?.code ?? "error",
              body?.error?.message ?? "Couldn't send the export. Try again.",
            ),
          );
      };
      xhr.onerror = () =>
        reject(new HomingApiError(503, "unreachable", "The upload stopped. Check your connection and try again."));
      xhr.send(form);
    });
  },
  async get(id: string): Promise<ImportStatus> {
    return toImport(await api<RawImport>(`imports/${encodeURIComponent(id)}`));
  },
  async recent(): Promise<ImportStatus[]> {
    return (await api<RawImport[]>("imports")).map(toImport);
  },
};

/** A goal and the saves that serve it (server/app/api/v1/threads.py). */
export type ThreadSummary = {
  id: string;
  title: string;
  summary: string | null;
  /** The person named it; rebuilds keep the name. */
  locked: boolean;
  saves: number;
  lastSavedAt: string | null;
};

export type ThreadDetail = ThreadSummary & { items: SaveListItem[] };

type RawThread = {
  id: string;
  title: string;
  summary: string | null;
  locked: boolean;
  saves: number;
  last_saved_at: string | null;
};

function toThread(raw: RawThread): ThreadSummary {
  return {
    id: raw.id,
    title: raw.title,
    summary: raw.summary,
    locked: raw.locked,
    saves: raw.saves,
    lastSavedAt: raw.last_saved_at,
  };
}

export const threadsApi = {
  async list(): Promise<{ items: ThreadSummary[]; unplaced: number }> {
    const page = await api<{ items: RawThread[]; unplaced: number }>("threads");
    return { items: page.items.map(toThread), unplaced: page.unplaced };
  },
  async get(id: string): Promise<ThreadDetail> {
    const raw = await api<RawThread & { items: (RawSave & { title: string | null; what: string | null })[] }>(
      `threads/${encodeURIComponent(id)}`,
    );
    return {
      ...toThread(raw),
      items: raw.items.map((i) => ({ ...toSave(i), title: i.title, what: i.what })),
    };
  },
  /** The person's own name for a goal; it locks the thread. */
  async rename(id: string, title: string): Promise<ThreadSummary> {
    return toThread(
      await api<RawThread>(`threads/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      }),
    );
  },
  /** What's it for? organises the whole pile again. */
  async rebuild(): Promise<void> {
    await api("threads/rebuild", { method: "POST" });
  },
};

export const searchApi = {
  /** By words and by meaning at once; no model call, so it runs as you type. */
  async search(q: string): Promise<SaveListItem[]> {
    const page = await api<{ items: (RawSave & { title: string | null; what: string | null })[] }>(
      `search?q=${encodeURIComponent(q)}&limit=12`,
    );
    return page.items.map((raw) => ({ ...toSave(raw), title: raw.title, what: raw.what }));
  },
};

/** One verified point on an answer page: its quote was found in the save it cites. */
export type AskPoint = { point: string; quote: string; saveId: string; title: string; savedAt: string };

export type AskStatus = {
  id: string;
  question: string;
  status: "working" | "done" | "failed";
  points: AskPoint[];
  /** Saves that may help, but Homing only knows their titles. */
  also: { saveId: string; title: string }[];
  notCovered: string[];
  considered: number;
  read: number;
  /** Muse Wonder's steps, in order: shown live while it works, then as how it was found. */
  steps: { kind: "search" | "open" | "refused" | "accepted"; text: string }[];
  /** When Muse Wonder ran it as an agent: its own searches, what it opened, what code refused. */
  agent: { model: string; turns: number; searches: string[]; opened: number; refusals: number } | null;
  error: string | null;
};

type RawAsk = {
  id: string;
  question: string;
  status: AskStatus["status"];
  error: string | null;
  answer: {
    points: { point: string; quote: string; save_id: string; title: string; saved_at: string }[];
    also?: { save_id: string; title: string }[];
    not_covered: string[];
    considered: number;
    read: number;
    agent?: AskStatus["agent"];
    steps?: AskStatus["steps"];
  } | null;
};

function toAsk(raw: RawAsk): AskStatus {
  const a = raw.answer;
  return {
    id: raw.id,
    question: raw.question,
    status: raw.status,
    error: raw.error,
    points: (a?.points ?? []).map((p) => ({
      point: p.point,
      quote: p.quote,
      saveId: p.save_id,
      title: p.title,
      savedAt: p.saved_at,
    })),
    also: (a?.also ?? []).map((x) => ({ saveId: x.save_id, title: x.title })),
    notCovered: a?.not_covered ?? [],
    considered: a?.considered ?? 0,
    read: a?.read ?? 0,
    agent: a?.agent ?? null,
    steps: a?.steps ?? [],
  };
}

export const askApi = {
  async ask(question: string): Promise<AskStatus> {
    return toAsk(await api<RawAsk>("asks", { method: "POST", body: JSON.stringify({ question }) }));
  },
  async get(id: string): Promise<AskStatus> {
    return toAsk(await api<RawAsk>(`asks/${encodeURIComponent(id)}`));
  },
  async recent(): Promise<AskStatus[]> {
    return (await api<RawAsk[]>("asks")).map(toAsk);
  },
};

/** Something What's it for? found on the web for a goal, after code's checks. */
export type Find = {
  id: string;
  goal: string | null;
  threadId: string | null;
  name: string;
  what: string;
  url: string;
  site: string;
  closes: string | null;
  fit: string;
  verdict: string;
  rules: { plain: string | null; quote: string | null; result: string | null }[];
  quotes: { label: string; quote: string }[];
  saveId: string | null;
};

export type DismissWhy = "wrong_country" | "not_my_stage" | "already_applied" | "not_interested";

type RawFind = Omit<Find, "threadId" | "saveId"> & { thread_id: string | null; save_id: string | null };

function toFind(raw: RawFind): Find {
  const { thread_id: threadId, save_id: saveId, ...rest } = raw;
  return { ...rest, threadId, saveId };
}

export const findsApi = {
  async list(threadId?: string): Promise<Find[]> {
    const query = threadId ? `?thread_id=${encodeURIComponent(threadId)}` : "";
    return (await api<RawFind[]>(`finds${query}`)).map(toFind);
  },
  /** Save it: from here every agent reads it like anything the person saved. */
  async keep(id: string): Promise<Find> {
    return toFind(await api<RawFind>(`finds/${encodeURIComponent(id)}/keep`, { method: "POST" }));
  },
  /** Not for me, with an optional reason the next run for this goal rules out. */
  async dismiss(id: string, why?: DismissWhy): Promise<void> {
    await api(`finds/${encodeURIComponent(id)}/dismiss`, {
      method: "POST",
      body: JSON.stringify({ why: why ?? null }),
    });
  },
  /** Look on the web for more for this goal now. */
  async findNow(threadId: string): Promise<void> {
    await api(`threads/${encodeURIComponent(threadId)}/find`, { method: "POST" });
  },
};
