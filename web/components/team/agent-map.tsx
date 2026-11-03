"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import { AgentBody } from "@/components/team/agent-mark";
import { AGENTS, FOUR } from "@/components/team/agents";
import type { Agent, AgentEvent, TeamOverview } from "@/lib/api";

type Point = { x: number; y: number };
type Four = Exclude<Agent, "system">;
type Layout = {
  w: number;
  h: number;
  hub: Point;
  you: Point;
  spot: Record<Four, Point>;
  rx: number;
  ry: number;
  captionY: number;
  label: string;
  // On a phone the map is drawn smaller, so its small text is set larger.
  small: string;
  tiny: string;
  caption: string;
  room: number;
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
  small: "text-[12px]",
  tiny: "text-[11px]",
  caption: "text-[13px]",
  room: 78,
};
// Phones: a taller map drawn at full size, not the wide one shrunk to half.
const TALL: Layout = {
  w: 360,
  h: 490,
  hub: { x: 180, y: 228 },
  you: { x: 180, y: 462 },
  spot: {
    what: { x: 88, y: 58 },
    true: { x: 272, y: 58 },
    for: { x: 88, y: 368 },
    when: { x: 272, y: 368 },
  },
  rx: 96,
  ry: 70,
  captionY: 326,
  label: "text-[14px]",
  small: "text-[14px]",
  tiny: "text-[13px]",
  caption: "text-[14px]",
  room: 40,
};

const AGENT_R = 24;
const HUB_R = 44;
const YOU_R = 17;
const GAP = 4;
const FLIGHT_MS = 900;
const LINGER_MS = 700;
const NEEDS = "#b45309";
// Actions that hand something to the person to decide.
const FOR_YOU = new Set(["surfaced", "prep_ready", "asked", "needs_answer"]);

const CALM = "(prefers-reduced-motion: reduce)";
const prefersCalm = () => window.matchMedia(CALM).matches;
function subscribeMotion(change: () => void) {
  const query = window.matchMedia(CALM);
  query.addEventListener("change", change);
  return () => query.removeEventListener("change", change);
}

/** The stretch of the line from a to b that lies outside both circles. */
function edge(a: Point, ra: number, b: Point, rb: number): [Point, Point] {
  const d = Math.hypot(b.x - a.x, b.y - a.y) || 1;
  const ux = (b.x - a.x) / d;
  const uy = (b.y - a.y) / d;
  return [
    { x: a.x + ux * ra, y: a.y + uy * ra },
    { x: b.x - ux * rb, y: b.y - uy * rb },
  ];
}

type Target = Point & { r: number; goalId: string | null };

/**
 * Your library in the middle, your largest goals around it, the four agents at the
 * corners and you at the bottom. A dot travels only when an agent posts a real event, along
 * the line from that agent to the goal it touched (or to you when it needs a decision), and
 * the circle it reaches ripples. An agent with jobs in hand breathes and says how many.
 */
export function AgentMap({
  overview,
  incoming,
  selected,
  onSelect,
  onNeedsYou,
}: {
  overview: TeamOverview;
  incoming: AgentEvent | null;
  selected: Agent | null;
  onSelect: (agent: Agent | null) => void;
  onNeedsYou: () => void;
}) {
  const box = useRef<HTMLElement>(null);
  const [tall, setTall] = useState(false);
  const calm = useSyncExternalStore(subscribeMotion, prefersCalm, () => false);
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
  const seen = useRef(new Set<number>());
  const dot = useRef<SVGCircleElement>(null);
  const [flight, setFlight] = useState<{
    agent: Four;
    line: [Point, Point];
    goalId: string | null;
  } | null>(null);
  const [ripple, setRipple] = useState<{
    key: number;
    at: Target;
    color: string;
  } | null>(null);
  const [caption, setCaption] = useState("Waiting for the next thing to do");

  useEffect(() => {
    // Fresh data re-runs this effect; each step still plays once.
    if (
      !incoming ||
      incoming.agent === "system" ||
      seen.current.has(incoming.id)
    )
      return;
    seen.current.add(incoming.id);
    queue.current.push(incoming);

    const next = () => {
      // Under a burst (an import), skip ahead so the map keeps up with what's happening now.
      if (queue.current.length > 6) queue.current = queue.current.slice(-3);
      const event = queue.current.shift();
      if (!event || event.agent === "system") {
        busy.current = false;
        return;
      }
      busy.current = true;
      const agent = event.agent as Four;
      // The event names its goal when it has one; otherwise the save's goal, if we know it.
      const goalId =
        event.threadId ??
        (event.saveId ? overview.goalOf[event.saveId] : undefined);
      const goal = goals.find((g) => g.id === goalId);
      const to: Target = FOR_YOU.has(event.action)
        ? { ...L.you, r: YOU_R, goalId: null }
        : goal
          ? { x: goal.x, y: goal.y, r: goal.r, goalId: goal.id }
          : { ...L.hub, r: HUB_R, goalId: null };
      const line = edge(L.spot[agent], AGENT_R + GAP, to, to.r + GAP);
      setFlight({ agent, line, goalId: to.goalId });

      const land = () => {
        setRipple({ key: event.id, at: to, color: AGENTS[agent].color });
        // What the agent did, in its own words, cut to fit the map.
        setCaption(
          event.summary.length > L.room
            ? `${event.summary.slice(0, L.room - 1).trimEnd()}…`
            : event.summary,
        );
        setTimeout(() => {
          setFlight(null);
          next();
        }, LINGER_MS);
      };
      if (calm || !dot.current) return land();
      const [from, end] = line;
      dot.current.setAttribute("cx", String(from.x));
      dot.current.setAttribute("cy", String(from.y));
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / FLIGHT_MS);
        const e = 1 - (1 - t) ** 3;
        dot.current?.setAttribute("cx", String(from.x + (end.x - from.x) * e));
        dot.current?.setAttribute("cy", String(from.y + (end.y - from.y) * e));
        if (t < 1) requestAnimationFrame(step);
        else land();
      };
      requestAnimationFrame(step);
    };
    if (!busy.current) next();
  }, [incoming, goals, overview.goalOf, L, calm]);

  const needs = overview.now.needsYou;

  return (
    <figure ref={box} className="glass rounded-[var(--radius-card)] p-3 sm:p-5">
      <svg
        viewBox={`0 0 ${L.w} ${L.h}`}
        className="w-full"
        role="img"
        aria-label="Your agents and your library"
      >
        {goals.map((g) => {
          const [a, b] = edge(L.hub, HUB_R, g, g.r);
          return (
            <line
              key={`s-${g.id}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--line)"
            />
          );
        })}
        {FOUR.map((agent) => {
          const [a, b] = edge(L.spot[agent], AGENT_R + GAP, L.hub, HUB_R + GAP);
          return (
            <line
              key={`l-${agent}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--muted)"
              strokeOpacity={0.35}
              strokeDasharray="2 6"
            />
          );
        })}
        {flight && (
          <line
            x1={flight.line[0].x}
            y1={flight.line[0].y}
            x2={flight.line[1].x}
            y2={flight.line[1].y}
            stroke={AGENTS[flight.agent].color}
            strokeOpacity={0.5}
            strokeWidth={1.5}
            strokeDasharray="3 5"
          />
        )}

        <circle
          cx={L.hub.x}
          cy={L.hub.y}
          r={HUB_R}
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
          className={`fill-ink-2 ${L.small}`}
        >
          your saves
        </text>

        {goals.map((g) => {
          const lit = flight?.goalId === g.id;
          return (
            <circle
              key={g.id}
              cx={g.x}
              cy={g.y}
              r={g.r}
              fill={lit ? AGENTS[flight.agent].color : "#fff"}
              stroke={lit ? AGENTS[flight.agent].color : "var(--muted)"}
              className="transition-colors duration-300"
            >
              <title>{`${g.title} · ${g.saves} ${g.saves === 1 ? "save" : "saves"}`}</title>
            </circle>
          );
        })}

        {ripple && (
          <circle
            key={ripple.key}
            cx={ripple.at.x}
            cy={ripple.at.y}
            r={ripple.at.r}
            fill="none"
            stroke={ripple.color}
            strokeWidth={2}
          >
            {!calm && (
              <>
                <animate
                  attributeName="r"
                  from={ripple.at.r}
                  to={ripple.at.r + 16}
                  dur="0.7s"
                  fill="freeze"
                />
                <animate
                  attributeName="stroke-opacity"
                  from="0.8"
                  to="0"
                  dur="0.7s"
                  fill="freeze"
                />
              </>
            )}
            {calm && <set attributeName="stroke-opacity" to="0" begin="0.7s" />}
          </circle>
        )}

        {FOUR.map((agent) => {
          const { x, y } = L.spot[agent];
          const picked = selected === agent;
          const jobs = overview.now.working[agent] ?? 0;
          const { color, label, job } = AGENTS[agent];
          return (
            <g
              key={agent}
              role="button"
              tabIndex={0}
              aria-label={`Show only ${label}`}
              aria-pressed={picked}
              onClick={() => onSelect(picked ? null : agent)}
              onKeyDown={(e) =>
                (e.key === "Enter" || e.key === " ") &&
                onSelect(picked ? null : agent)
              }
              className="cursor-pointer outline-none"
            >
              {jobs > 0 && (
                <circle
                  cx={x}
                  cy={y}
                  r={AGENT_R + 7}
                  fill={color}
                  fillOpacity={0.12}
                  stroke={color}
                  strokeOpacity={0.35}
                >
                  {!calm && (
                    <animate
                      attributeName="r"
                      values={`${AGENT_R + 5};${AGENT_R + 10};${AGENT_R + 5}`}
                      dur="2.4s"
                      repeatCount="indefinite"
                    />
                  )}
                </circle>
              )}
              {picked && (
                <circle
                  cx={x}
                  cy={y}
                  r={AGENT_R + 9}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                />
              )}
              <AgentBody agent={agent} x={x} y={y} r={AGENT_R} />
              <text
                x={x}
                y={y + 46}
                textAnchor="middle"
                className={`fill-ink font-display font-bold ${L.label}`}
              >
                {label}
              </text>
              {jobs > 0 ? (
                <text
                  x={x}
                  y={y + 64}
                  textAnchor="middle"
                  fill={color}
                  className={`font-semibold ${L.small}`}
                >
                  Working on {jobs}
                </text>
              ) : (
                <text
                  x={x}
                  y={y + 64}
                  textAnchor="middle"
                  className="fill-ink-2 text-[12px] max-sm:hidden"
                >
                  {job}
                </text>
              )}
            </g>
          );
        })}

        <text
          x={L.hub.x}
          y={L.captionY}
          textAnchor="middle"
          className={`fill-ink-2 font-semibold ${L.caption}`}
        >
          {caption}
        </text>

        <g
          role={needs ? "button" : undefined}
          tabIndex={needs ? 0 : undefined}
          aria-label={needs ? `${needs} need your answer` : undefined}
          onClick={needs ? onNeedsYou : undefined}
          onKeyDown={(e) =>
            needs && (e.key === "Enter" || e.key === " ") && onNeedsYou()
          }
          className={needs ? "cursor-pointer outline-none" : ""}
        >
          {needs > 0 && (
            <circle
              cx={L.you.x}
              cy={L.you.y}
              r={YOU_R + 5}
              fill="none"
              stroke={NEEDS}
              strokeWidth={1.5}
            >
              {!calm && (
                <>
                  <animate
                    attributeName="r"
                    values={`${YOU_R + 3};${YOU_R + 9};${YOU_R + 3}`}
                    dur="1.8s"
                    repeatCount="indefinite"
                  />
                  <animate
                    attributeName="stroke-opacity"
                    values="0.9;0.2;0.9"
                    dur="1.8s"
                    repeatCount="indefinite"
                  />
                </>
              )}
            </circle>
          )}
          <circle cx={L.you.x} cy={L.you.y} r={YOU_R} fill="var(--ink)" />
          <text
            x={L.you.x}
            y={L.you.y + 4}
            textAnchor="middle"
            className={`fill-white font-semibold ${L.tiny}`}
          >
            you
          </text>
          {needs > 0 && (
            <>
              <circle cx={L.you.x + 14} cy={L.you.y - 13} r={9} fill={NEEDS} />
              <text
                x={L.you.x + 14}
                y={L.you.y - 9.5}
                textAnchor="middle"
                className="fill-white text-[10px] font-bold"
              >
                {needs > 9 ? "9+" : needs}
              </text>
            </>
          )}
          {needs > 0 ? (
            <text
              x={L.you.x + 30}
              y={L.you.y + 4}
              fill={NEEDS}
              className={`font-semibold ${L.small}`}
            >
              {tall
                ? "Need you"
                : `${needs} ${needs === 1 ? "save needs" : "saves need"} your answer`}
            </text>
          ) : (
            <text
              x={L.you.x + 28}
              y={L.you.y + 4}
              className="fill-ink-2 text-[12px] max-sm:hidden"
            >
              You decide: Use it · Not for me · Later
            </text>
          )}
        </g>

        <circle
          ref={dot}
          cx={-20}
          cy={-20}
          r={flight ? 6 : 0}
          fill={flight ? AGENTS[flight.agent].color : "transparent"}
        />
      </svg>
      <figcaption className="mt-1 px-1 text-xs text-muted">
        Nothing here moves unless an agent did something. Click an agent to see
        only its work.
      </figcaption>
    </figure>
  );
}
