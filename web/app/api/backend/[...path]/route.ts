import { getServerSession } from "next-auth";
import { NextResponse, type NextRequest } from "next/server";

import { authOptions } from "@/lib/auth";
import { BACKEND_URL, clientHeaders, errorResponse, identityHeaders } from "@/lib/server/backend";

/** Forwards /api/backend/* to the Homing API with the user's identity attached. */
async function proxy(req: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !session.user.email) {
    return errorResponse(401, "unauthorized", "Please sign in again.");
  }
  const identity = identityHeaders(session);
  if (!identity) {
    return errorResponse(500, "not_configured", "Homing isn't set up to reach its server.");
  }

  const { path } = await ctx.params;
  const target = `${BACKEND_URL}/api/v1/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const hasBody = !["GET", "HEAD"].includes(req.method);

  try {
    const res = await fetch(target, {
      method: req.method,
      headers: {
        Accept: "application/json",
        ...(hasBody ? { "Content-Type": req.headers.get("content-type") ?? "application/json" } : {}),
        ...identity,
        ...clientHeaders(req),
      },
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
    });
    const disposition = res.headers.get("content-disposition"); // e.g. a calendar file
    return new NextResponse(res.body, {
      status: res.status,
      headers: {
        "Content-Type": res.headers.get("content-type") ?? "application/json",
        ...(disposition ? { "Content-Disposition": disposition } : {}),
      },
    });
  } catch {
    return errorResponse(503, "unreachable", "Homing's server isn't reachable right now. Try again.");
  }
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
