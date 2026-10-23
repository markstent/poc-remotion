import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";

export type ColleaguePose = "idle" | "point" | "shrug" | "cheer" | "oops";

export type ColleagueMood = "happy" | "neutral" | "oops";

export interface ColleagueProps {
  pose: ColleaguePose;
  mood?: ColleagueMood;
  /** Rendered height in pixels. Width follows the 200:248 aspect ratio. */
  size: number;
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  bodyColor?: string;
  eyeColor?: string;
  smileColor?: string;
}

/** Fixed internal coordinate system: 200 wide, 248 tall. */
const VIEW_WIDTH = 200;
const VIEW_HEIGHT = 248;

/**
 * Arm polylines per pose, left shoulder first. Shoulders sit at (58,138) and
 * (142,138). Two points is a straight arm; three points adds an elbow.
 */
const ARM_POSES: Record<ColleaguePose, { left: string; right: string }> = {
  idle: { left: "58,138 40,193", right: "142,138 160,193" },
  point: { left: "58,138 42,193", right: "142,138 186,92" },
  shrug: { left: "58,140 30,158 38,124", right: "142,140 170,158 162,124" },
  cheer: { left: "58,138 36,90", right: "142,138 164,90" },
  oops: { left: "58,138 50,196", right: "142,138 150,196" }
};

const ARM_STROKE_WIDTH = 15;

function Arms({ pose, color }: { pose: ColleaguePose; color: string }): JSX.Element {
  const { left, right } = ARM_POSES[pose];
  const stroke = {
    stroke: color,
    strokeWidth: ARM_STROKE_WIDTH,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    fill: "none"
  } as const;
  return (
    <g>
      <polyline points={left} {...stroke} />
      <polyline points={right} {...stroke} />
    </g>
  );
}

function Eyes({ mood, color }: { mood: ColleagueMood; color: string }): JSX.Element {
  const radius = mood === "oops" ? 9 : 7;
  return (
    <g fill={color}>
      <circle cx={84} cy={58} r={radius} />
      <circle cx={116} cy={58} r={radius} />
    </g>
  );
}

function Mouth({ mood, color }: { mood: ColleagueMood; color: string }): JSX.Element {
  if (mood === "oops") {
    return <circle cx={100} cy={92} r={9} fill={color} />;
  }
  if (mood === "neutral") {
    return (
      <line
        x1={84}
        y1={90}
        x2={116}
        y2={90}
        stroke={color}
        strokeWidth={7}
        strokeLinecap="round"
      />
    );
  }
  return (
    <path
      d="M 78 82 Q 100 102 122 82"
      stroke={color}
      strokeWidth={7}
      strokeLinecap="round"
      fill="none"
    />
  );
}

export function Colleague({
  pose,
  mood = "happy",
  size,
  bodyColor = "#1D4757",
  eyeColor = "#FFFFFF",
  smileColor = "#C4F600"
}: ColleagueProps): JSX.Element {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Idle bob: a fixed-config spring eases the amplitude in over the first
  // frames, then a deterministic sine carries the gentle hover. Both inputs
  // (frame, fps) come from the Remotion timeline, so output is reproducible.
  const settle = spring({
    frame,
    fps,
    config: { damping: 10, stiffness: 90, mass: 0.6 }
  });
  const bob = pose === "idle" ? Math.sin(frame * 0.12) * 4 * settle : 0;

  return (
    <svg
      width={(size * VIEW_WIDTH) / VIEW_HEIGHT}
      height={size}
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      role="img"
      aria-label={`Colleague character, ${pose} pose`}
    >
      <g transform={`translate(0 ${bob})`}>
        {/* Body */}
        <rect x={54} y={110} width={92} height={132} rx={30} fill={bodyColor} />
        {/* Head */}
        <circle cx={100} cy={68} r={46} fill={bodyColor} />
        {/* Arms (darkTeal, drawn under nothing, same flat colour as the body) */}
        <Arms pose={pose} color={bodyColor} />
        <Eyes mood={mood} color={eyeColor} />
        <Mouth mood={mood} color={smileColor} />
      </g>
    </svg>
  );
}
