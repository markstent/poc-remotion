import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import type { SceneProps } from "./types";

export interface NewsGridProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  cardColor?: string;
  stripColor?: string;
  textColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";

/** News grid scene: 2x2 white cards, each with a lime lesson strip, on darkTeal. */
export function NewsGrid({
  scene,
  fps,
  background = "#1D4757",
  cardColor = "#FFFFFF",
  stripColor = "#C4F600",
  textColor = "#1D4757"
}: NewsGridProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationFrames = Math.round(scene.seconds * fps);

  const cardWidth = width * 0.42;
  const cardHeight = height * 0.36;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background,
        overflow: "hidden",
        display: "grid",
        gridTemplateColumns: `repeat(2, ${cardWidth}px)`,
        gridAutoRows: `${cardHeight}px`,
        gap: `${height * 0.04}px ${width * 0.025}px`,
        alignItems: "center",
        justifyContent: "center",
        alignContent: "center"
      }}
    >
      {[0, 1, 2, 3].map((i) => {
        // Cards land one fifth of the scene apart, so the last lands mid-scene.
        const cardIn = spring({
          frame,
          fps,
          delay: Math.round((i * durationFrames) / 5),
          config: SPRING_CONFIG
        });
        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "stretch",
              background: cardColor,
              borderRadius: 36,
              overflow: "hidden",
              opacity: cardIn,
              transform: `translateY(${(1 - cardIn) * 60}px)`
            }}
          >
            <div style={{ width: 22, flexShrink: 0, background: stripColor }} />
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                padding: `0 ${width * 0.02}px`,
                fontSize: 38,
                lineHeight: 1.25,
                fontWeight: 400,
                color: textColor,
                fontFamily: FONT_STACK
              }}
            >
              {scene.on_screen[i] ?? ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}
