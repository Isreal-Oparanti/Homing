import { AGENTS } from "@/components/team/agents";
import type { Agent } from "@/lib/api";

/** An agent's own shape, drawn at (x, y) inside an SVG: a coloured body with two eyes. */
export function AgentBody({
  agent,
  x,
  y,
  r,
}: {
  agent: Agent;
  x: number;
  y: number;
  r: number;
}) {
  const { color, shape } = AGENTS[agent];
  const eye = { rx: r * 0.14, ry: r * 0.19 };
  return (
    <g>
      {shape === "circle" && <circle cx={x} cy={y} r={r} fill={color} />}
      {shape === "square" && (
        <rect
          x={x - r * 0.9}
          y={y - r * 0.9}
          width={r * 1.8}
          height={r * 1.8}
          rx={r * 0.5}
          fill={color}
        />
      )}
      {shape === "hex" && (
        <polygon
          fill={color}
          strokeLinejoin="round"
          stroke={color}
          strokeWidth={r * 0.18}
          points={Array.from({ length: 6 }, (_, i) => {
            const t = Math.PI / 6 + (i * Math.PI) / 3;
            return `${x + Math.cos(t) * r * 0.98},${y + Math.sin(t) * r * 0.98}`;
          }).join(" ")}
        />
      )}
      {shape === "diamond" && (
        <rect
          x={x - r * 0.78}
          y={y - r * 0.78}
          width={r * 1.56}
          height={r * 1.56}
          rx={r * 0.32}
          fill={color}
          transform={`rotate(45 ${x} ${y})`}
        />
      )}
      <ellipse cx={x - r * 0.3} cy={y - r * 0.08} {...eye} fill="#fff" />
      <ellipse cx={x + r * 0.3} cy={y - r * 0.08} {...eye} fill="#fff" />
    </g>
  );
}

/** The agent as a small icon, for the feed and the save card. */
export function AgentMark({
  agent,
  size = 20,
}: {
  agent: Agent;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      aria-hidden
      className="shrink-0"
    >
      <AgentBody agent={agent} x={20} y={20} r={16} />
    </svg>
  );
}
