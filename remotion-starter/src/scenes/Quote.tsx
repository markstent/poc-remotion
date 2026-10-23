import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import type { StoryboardScene } from "../lib/types";

/**
 * Shared props for every scene component. Declared in each scene file with an
 * identical shape so scene files stay self-contained; the parent composition
 * wraps each scene in a <Sequence> lasting `scene.seconds * fps` frames.
 */
export type SceneProps = {
  scene: StoryboardScene;
  fps: number;
};

export interface QuoteProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  lineColor?: string;
  bubbleColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";
const BUBBLE_TEXT = "What's missing?";

/** Quote scene: full-bleed lime, huge darkTeal line, white speech bubble pop-in. */
export function Quote({
  scene,
  fps,
  background = "#C4F600",
  lineColor = "#1D4757",
  bubbleColor = "#FFFFFF"
}: QuoteProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const line = scene.on_screen[0] ?? "";

  const lineIn = spring({ frame, fps, delay: 2, config: SPRING_CONFIG });
  const bubbleIn = spring({ frame, fps, delay: 14, config: SPRING_CONFIG });
  const bubbleScale = interpolate(bubbleIn, [0, 1], [0.6, 1]);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background,
        overflow: "hidden"
      }}
    >
      <div
        style={{
          position: "absolute",
          left: width * 0.1,
          top: height * 0.22,
          width: width * 0.8,
          textAlign: "center",
          fontSize: 132,
          lineHeight: 1.08,
          fontWeight: 700,
          color: lineColor,
          fontFamily: FONT_STACK,
          opacity: lineIn,
          transform: `translateY(${(1 - lineIn) * 60}px)`
        }}
      >
        {line}
      </div>
      <div
        style={{
          position: "absolute",
          left: width * 0.5,
          top: height * 0.64,
          opacity: bubbleIn,
          transform: `translateX(-50%) scale(${bubbleScale})`
        }}
      >
        <div
          style={{
            background: bubbleColor,
            borderRadius: 44,
            padding: "34px 56px",
            fontSize: 60,
            fontWeight: 700,
            color: lineColor,
            fontFamily: FONT_STACK,
            whiteSpace: "nowrap"
          }}
        >
          {BUBBLE_TEXT}
        </div>
        <div
          style={{
            width: 40,
            height: 40,
            background: bubbleColor,
            borderRadius: 8,
            transform: "rotate(45deg)",
            margin: "-24px 0 0 88px"
          }}
        />
      </div>
    </div>
  );
}
