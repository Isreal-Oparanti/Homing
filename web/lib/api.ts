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
