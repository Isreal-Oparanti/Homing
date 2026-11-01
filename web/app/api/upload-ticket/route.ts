import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";

import { authOptions } from "@/lib/auth";
import { BACKEND_URL, errorResponse, uploadTicket } from "@/lib/server/backend";

/** Where the browser sends files, and the ticket that says who is sending them. */
export async function POST() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id || !session.user.email) {
    return errorResponse(401, "unauthorized", "Please sign in again.");
  }
  const ticket = uploadTicket(session);
  if (!ticket) {
    return errorResponse(
      500,
      "not_configured",
      "Homing isn't set up to reach its server.",
    );
  }
  // `api` is for the other upload, a WhatsApp export (POST /imports/whatsapp).
  return NextResponse.json({ url: `${BACKEND_URL}/api/v1/saves/file`, api: `${BACKEND_URL}/api/v1`, ticket });
}
