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
    createdAt: raw.created_at,
  };
}

export type TeamPage = { items: AgentEvent[]; nextCursor: string | null };

export const teamApi = {
  async list(cursor?: string): Promise<TeamPage> {
    const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
    const page = await api<{ items: RawAgentEvent[]; next_cursor: string | null }>(
      `team${query}`,
    );
    return { items: page.items.map(toAgentEvent), nextCursor: page.next_cursor };
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

export type SaveCard = { save: SaveSummary; what: Reading | null; copies: Copy[]; pending: Answer[] };

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
};

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
      copies: RawCopy[];
      pending: Answer[];
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
      copies: raw.copies.map((c) => ({
        id: c.id,
        kind: c.kind,
        sourceUrl: c.source_url,
        chars: c.chars,
        excerpt: c.excerpt,
      })),
      pending: raw.pending,
    };
  },
};
