"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { AgentBody } from "@/components/team/agent-mark";
import { AGENTS, FOUR } from "@/components/team/agents";
import type { Agent, AgentEvent, TeamOverview } from "@/lib/api";

type Point = { x: number; y: number };
type Layout = {
  w: number;
  h: number;
  hub: Point;
  you: Point;
  spot: Record<Exclude<Agent, "system">, Point>;
  rx: number;
  ry: number;
  captionY: number;
  label: string;
};

// Wide screens: agents at the corners of a landscape map.
const WIDE: Layout = {
  w: 680,
  h: 370,
  hub: { x: 340, y: 168 },
  you: { x: 340, y: 338 },
  spot: {
    what: { x: 96, y: 78 },
    true: { x: 584, y: 78 },
    for: { x: 96, y: 246 },
    when: { x: 584, y: 246 },
  },
  rx: 128,
  ry: 80,
  captionY: 286,
  label: "text-[15px]",
};
// Phones: a taller map drawn at full size, not the wide one shrunk to half.
const TALL: Layout = {
  w: 360,
  h: 490,
  hub: { x: 180, y: 228 },
  you: { x: 180, y: 466 },
  spot: {
    what: { x: 88, y: 58 },
    true: { x: 272, y: 58 },
    for: { x: 88, y: 368 },
    when: { x: 272, y: 368 },
  },
  rx: 96,
  ry: 70,
  captionY: 326,
  label: "text-[13px]",
};
const FLIGHT_MS = 900;
const LINGER_MS = 700;
// Actions that hand something to the person to decide.
const FOR_YOU = new Set(["surfaced", "prep_ready", "asked", "needs_answer"]);

/**
 * Your library in the middle, your largest goals around it, the four agents at the
 * corners and you at the bottom. A dot travels only when an agent posts a real event:
 * from that agent to the goal the save belongs to, or to you when it needs a decision.
 */
export function AgentMap({
  overview,
  incoming,
  selected,
  onSelect,
}: {
  overview: TeamOverview;
  incoming: AgentEvent | null;
  selected: Agent | null;
  onSelect: (agent: Agent | null) => void;
}) {
  const box = useRef<HTMLElement>(null);
  const [tall, setTall] = useState(false);
  useEffect(() => {
    if (!box.current) return;
    const watch = new ResizeObserver(([e]) =>
      setTall(e.contentRect.width < 520),
    );
    watch.observe(box.current);
    return () => watch.disconnect();
  }, []);
  const L = tall ? TALL : WIDE;

  const goals = useMemo(() => {
    const most = Math.max(1, ...overview.goals.map((g) => g.saves));
    return overview.goals.map((g, i) => {
      const a =
        -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(1, overview.goals.length);
      return {
        ...g,
        x: L.hub.x + Math.cos(a) * L.rx,
        y: L.hub.y + Math.sin(a) * L.ry,
        r: 5 + 6 * Math.sqrt(g.saves / most),
      };
    });
  }, [overview.goals, L]);

  const queue = useRef<AgentEvent[]>([]);
  const busy = useRef(false);
  const dot = useRef<SVGCircleElement>(null);
  const [active, setActive] = useState<{
    agent: Agent;
    to: Point;
    goalId: string | null;
  } | null>(null);
  const [caption, setCaption] = useState("Waiting for the next thing to do");

  useEffect(() => {
    if (!incoming || incoming.agent === "system") return;
    queue.current.push(incoming);
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const next = () => {
      // Under a burst (an import), skip ahead so the map keeps up with what's happening now.
      if (queue.current.length > 6) queue.current = queue.current.slice(-3);
      const event = queue.current.shift();
      if (!event || event.agent === "system") {
        busy.current = false;
        return;
      }
      busy.current = true;
      const from = L.spot[event.agent];
      // The event names its goal when it has one; otherwise the save's goal, if we know it.
      const goalId =
        event.threadId ??
        (event.saveId ? overview.goalOf[event.saveId] : undefined);
      const goal = goals.find((g) => g.id === goalId);
      const to: Point = FOR_YOU.has(event.action) ? L.you : (goal ?? L.hub);
      setActive({ agent: event.agent, to, goalId: goal?.id ?? null });
      const land = () => {
        // What the agent did, in its own words, cut to fit the map.
        const room = L === TALL ? 44 : 78;
        setCaption(
          event.summary.length > room
            ? `${event.summary.slice(0, room - 1).trimEnd()}…`
            : event.summary,
        );
        setTimeout(() => {
          setActive(null);
          next();
        }, LINGER_MS);
      };
      if (reduce || !dot.current) return land();
      dot.current.setAttribute("cx", String(from.x));
      dot.current.setAttribute("cy", String(from.y));
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / FLIGHT_MS);
        const e = 1 - (1 - t) ** 3;
        dot.current?.setAttribute("cx", String(from.x + (to.x - from.x) * e));
        dot.current?.setAttribute("cy", String(from.y + (to.y - from.y) * e));
        if (t < 1) requestAnimationFrame(step);
        else land();
      };
      requestAnimationFrame(step);
    };
    if (!busy.current) next();
  }, [incoming, goals, overview.goalOf, L]);

  return (
    <figure ref={box} className="glass rounded-[var(--radius-card)] p-3 sm:p-5">
      <svg
        viewBox={`0 0 ${L.w} ${L.h}`}
        className="w-full"
        role="img"
        aria-label="Your agents and your library"
      >
        {goals.map((g) => (
          <line
            key={`s-${g.id}`}
            x1={L.hub.x}
            y1={L.hub.y}
            x2={g.x}
            y2={g.y}
            stroke="var(--line)"
            strokeWidth={1}
          />
        ))}
        {FOUR.map((a) => (
          <line
            key={`l-${a}`}
            x1={L.spot[a].x}
            y1={L.spot[a].y}
            x2={L.hub.x}
            y2={L.hub.y}
            stroke="var(--line)"
            strokeWidth={1}
            strokeDasharray="2 6"
          />
        ))}
        {active && (
          <line
            x1={L.spot[active.agent as keyof typeof L.spot].x}
            y1={L.spot[active.agent as keyof typeof L.spot].y}
            x2={active.to.x}
            y2={active.to.y}
            stroke={AGENTS[active.agent].color}
            strokeOpacity={0.45}
            strokeWidth={1.5}
            strokeDasharray="3 5"
          />
        )}

        <circle
          cx={L.hub.x}
          cy={L.hub.y}
          r={44}
          fill="#fff"
          stroke="var(--line)"
        />
        <text
          x={L.hub.x}
          y={L.hub.y - 6}
          textAnchor="middle"
          className="fill-ink font-display text-[22px] font-extrabold"
        >
          {overview.saves}
        </text>
        <text
          x={L.hub.x}
          y={L.hub.y + 14}
          textAnchor="middle"
          className="fill-ink-2 text-[12px]"
        >
          your saves
        </text>

        {goals.map((g) => {
          const lit = active?.goalId === g.id;
          return (
            <circle
              key={g.id}
              cx={g.x}
              cy={g.y}
              r={lit ? g.r + 2 : g.r}
              fill={lit ? AGENTS[active.agent].color : "#fff"}
              stroke={lit ? AGENTS[active.agent].color : "var(--muted)"}
              strokeWidth={1}
              className="transition-all duration-300"
            >
              <title>{`${g.title} · ${g.saves} ${g.saves === 1 ? "save" : "saves"}`}</title>
            </circle>
          );
        })}

        {FOUR.map((a) => {
          const { x, y } = L.spot[a];
          const on = active?.agent === a;
          const picked = selected === a;
          return (
            <g
              key={a}
              role="button"
              tabIndex={0}
              aria-label={`Show only ${AGENTS[a].label}`}
              aria-pressed={picked}
              onClick={() => onSelect(picked ? null : a)}
              onKeyDown={(e) =>
                (e.key === "Enter" || e.key === " ") &&
                onSelect(picked ? null : a)
              }
              className="cursor-pointer outline-none"
            >
              {(on || picked) && (
                <circle
                  cx={x}
                  cy={y}
                  r={33}
                  fill="none"
                  stroke={AGENTS[a].color}
                  strokeWidth={picked ? 2 : 1.5}
                  strokeOpacity={picked ? 0.9 : 0.5}
                  className={
                    on
                      ? "origin-center animate-ping [animation-duration:1.4s] [transform-box:fill-box]"
                      : ""
                  }
                />
              )}
              <AgentBody agent={a} x={x} y={y} r={24} />
              <text
                x={x}
                y={y + 46}
                textAnchor="middle"
                className={`fill-ink font-display font-bold ${L.label}`}
              >
                {AGENTS[a].label}
              </text>
              <text
                x={x}
                y={y + 64}
                textAnchor="middle"
                className="fill-ink-2 text-[12px] max-sm:hidden"
              >
                {AGENTS[a].job}
              </text>
            </g>
          );
        })}

        <text
          x={L.hub.x}
          y={L.captionY}
          textAnchor="middle"
          className="fill-ink-2 text-[13px] font-semibold"
        >
          {caption}
        </text>

        <circle cx={L.you.x} cy={L.you.y} r={17} fill="var(--ink)" />
        <text
          x={L.you.x}
          y={L.you.y + 4}
          textAnchor="middle"
          className="fill-white text-[11px] font-semibold"
        >
          you
        </text>
        <text
          x={L.you.x + 28}
          y={L.you.y + 4}
          className="fill-ink-2 text-[12px] max-sm:hidden"
        >
          You decide: Use it · Not for me · Later
        </text>

        <circle
          ref={dot}
          cx={-20}
          cy={-20}
          r={active ? 6 : 0}
          fill={active ? AGENTS[active.agent].color : "transparent"}
        />
      </svg>
      <figcaption className="mt-1 px-1 text-xs text-muted">
        Nothing here moves unless an agent did something. Click an agent to see
        only its work.
      </figcaption>
    </figure>
  );
}
