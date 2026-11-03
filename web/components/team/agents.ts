import type { Agent } from "@/lib/api";

export type AgentShape = "circle" | "hex" | "square" | "diamond";

/**
 * Each agent is named after the question it answers (docs/08-frontend.md), and keeps one
 * shape and one colour from the app's palette everywhere it appears.
 */
export const AGENTS: Record<
  Agent,
  {
    label: string;
    short: string;
    job: string;
    color: string;
    shape: AgentShape;
  }
> = {
  what: {
    label: "What is it?",
    short: "What",
    job: "Reads every save",
    color: "#d2402f",
    shape: "circle",
  },
  true: {
    label: "Is it true?",
    short: "True",
    job: "Opens the official page",
    color: "#1f7a4d",
    shape: "hex",
  },
  for: {
    label: "What's it for?",
    short: "For",
    job: "Finds your goals",
    color: "#16181b",
    shape: "square",
  },
  when: {
    label: "When will you need it?",
    short: "When",
    job: "Brings it back on time",
    color: "#b45309",
    shape: "diamond",
  },
  system: {
    label: "Homing",
    short: "Homing",
    job: "Runs the team",
    color: "#868a90",
    shape: "circle",
  },
};

/** The four agents, in the order a save meets them. */
export const FOUR: Exclude<Agent, "system">[] = ["what", "true", "for", "when"];
