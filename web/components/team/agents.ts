import { CalendarClock, House, ScanText, ShieldCheck, Waypoints, type LucideIcon } from "lucide-react";

import type { Agent } from "@/lib/api";

/** Each agent is named after the question it answers (docs/08-frontend.md). */
export const AGENTS: Record<Agent, { label: string; Icon: LucideIcon }> = {
  what: { label: "What is it?", Icon: ScanText },
  true: { label: "Is it true?", Icon: ShieldCheck },
  for: { label: "What's it for?", Icon: Waypoints },
  when: { label: "When will you need it?", Icon: CalendarClock },
  system: { label: "Homing", Icon: House },
};
