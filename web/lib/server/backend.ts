import "server-only";

import type { Session } from "next-auth";
import { NextResponse } from "next/server";

/** The Homing API. Only this server talks to it (docs/adr/0005-auth-proxy.md). */
export const BACKEND_URL = (process.env.HOMING_API_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

const ASCII = /^[\x20-\x7E]*$/;

/** Headers that tell the API who is asking. Returns null when the proxy isn't configured. */
export function identityHeaders(session: Session): Record<string, string> | null {
  const secret = process.env.HOMING_PROXY_SECRET;
  if (!secret) return null;
  const { id, email, name } = session.user;
  return {
    "X-Homing-Proxy-Secret": secret,
    "X-Homing-User-Id": id,
    "X-Homing-User-Email": email ?? "",
    // Header values must be plain ASCII; skip names that aren't.
    ...(name && ASCII.test(name) ? { "X-Homing-User-Name": name } : {}),
  };
}

export function errorResponse(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, details: {} } }, { status });
}
