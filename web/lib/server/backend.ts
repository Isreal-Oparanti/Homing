import "server-only";

import { createHmac } from "node:crypto";

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

/**
 * The visitor's address, so the API can count requests per visitor on the shared demo account
 * (server/app/core/ratelimit.py). Vercel sets these headers itself.
 */
export function clientHeaders(req: Request): Record<string, string> {
  const ip =
    req.headers.get("x-real-ip") ?? req.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  return ip && ASCII.test(ip) ? { "X-Homing-Client-IP": ip.slice(0, 64) } : {};
}

const TICKET_SECONDS = 300; // server/app/core/auth.py

/**
 * A short-lived ticket that lets the browser send files straight to the API: Vercel caps
 * request bodies at 4.5 MB, and files may be 10 MB. Signed like server/app/core/auth.py.
 */
export function uploadTicket(session: Session): string | null {
  const secret = process.env.HOMING_PROXY_SECRET;
  if (!secret) return null;
  const { id, email, name } = session.user;
  const payload = {
    uid: id,
    email: email ?? "",
    ...(name ? { name } : {}),
    exp: Math.floor(Date.now() / 1000) + TICKET_SECONDS,
  };
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const key = createHmac("sha256", secret).update("upload-ticket").digest();
  return `${body}.${createHmac("sha256", key).update(body).digest("base64url")}`;
}

export function errorResponse(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, details: {} } }, { status });
}
