import { getServerSession } from "next-auth";
import type { NextRequest } from "next/server";

import { authOptions } from "@/lib/auth";
import { BACKEND_URL, clientHeaders, errorResponse, identityHeaders } from "@/lib/server/backend";

/** Relays the API's live event stream. EventSource reconnects with Last-Event-ID on its own. */
export async function GET(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !session.user.email) {
    return errorResponse(401, "unauthorized", "Please sign in again.");
  }
  const identity = identityHeaders(session);
  if (!identity) {
    return errorResponse(500, "not_configured", "Homing isn't set up to reach its server.");
  }

  const lastEventId = req.headers.get("last-event-id");
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/events/stream`, {
      headers: {
        Accept: "text/event-stream",
        ...identity,
        ...clientHeaders(req),
        ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
      },
      cache: "no-store",
      signal: req.signal,
    });
    if (!res.ok || !res.body) {
      return errorResponse(res.status || 503, "stream_unavailable", "The live feed isn't available.");
    }
    return new Response(res.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch {
    return errorResponse(503, "unreachable", "Homing's server isn't reachable right now.");
  }
}
