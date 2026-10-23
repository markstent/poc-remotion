import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import type { SceneProps } from "./types";

export interface AnalogyProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  lineColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";
const SVG_VIEW_WIDTH = 1000;
const SVG_VIEW_HEIGHT = 420;
const WHEEL_POSITIONS = [160, 350, 745] as const;

/**
 * Analogy scene: a flat darkTeal lorry carrying one white envelope drives in
 * on lime, with a darkTeal caption line. Lorry and envelope are primitive
 * shapes only; motion is spring driven and deterministic.
 */
export function Analogy({
  scene,
  fps,
  background = "#C4F600",
  lineColor = "#1D4757"
}: AnalogyProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationFrames = Math.round(scene.seconds * fps);

  const truckIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.03), config: SPRING_CONFIG });
  const captionIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.3), config: SPRING_CONFIG });

  const svgWidth = width * 0.6;
  const svgX = interpolate(truckIn, [0, 1], [-svgWidth * 1.2, 0]);

  return (
    <div style={{ position: "absolute", inset: 0, background, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: height * 0.16,
          textAlign: "center",
          fontSize: 64,
          lineHeight: 1.1,
          fontWeight: 700,
          color: lineColor,
          fontFamily: FONT_STACK,
          opacity: captionIn,
          transform: `translateY(${(1 - captionIn) * 50}px)`
        }}
      >
        {scene.on_screen[0] ?? ""}
      </div>
      <div
        style={{
          position: "absolute",
          bottom: height * 0.1,
          left: svgX,
          width: svgWidth
        }}
      >
        <svg
          width={svgWidth}
          height={(svgWidth * SVG_VIEW_HEIGHT) / SVG_VIEW_WIDTH}
          viewBox={`0 0 ${SVG_VIEW_WIDTH} ${SVG_VIEW_HEIGHT}`}
          role="img"
          aria-label="Flat lorry carrying one envelope"
        >
          {/* Envelope sits inside the trailer bed, so draw it before the bed */}
          <rect
            x={110}
            y={70}
            width={340}
            height={210}
            rx={12}
            fill="#FFFFFF"
            stroke={lineColor}
            strokeWidth={12}
          />
          <path
            d="M 116 82 L 280 200 L 444 82"
            fill="none"
            stroke={lineColor}
            strokeWidth={12}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {/* Trailer bed */}
          <rect x={40} y={210} width={570} height={110} rx={22} fill={lineColor} />
          {/* Cab and window */}
          <rect x={650} y={150} width={200} height={170} rx={22} fill={lineColor} />
          <rect x={690} y={185} width={110} height={70} rx={14} fill="#FFFFFF" />
          {/* Wheels */}
          {WHEEL_POSITIONS.map((cx) => (
            <g key={cx}>
              <circle cx={cx} cy={345} r={54} fill={lineColor} />
              <circle cx={cx} cy={345} r={22} fill="#FFFFFF" />
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
