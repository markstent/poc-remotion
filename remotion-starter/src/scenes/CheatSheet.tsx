import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import type { SceneProps } from "./types";

export interface CheatSheetProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  panelColor?: string;
  badgeColor?: string;
  textColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";

/** Cheat sheet scene: three rounded summary panels with lime number badges. */
export function CheatSheet({
  scene,
  fps,
  background = "#1D4757",
  panelColor = "#FFFFFF",
  badgeColor = "#C4F600",
  textColor = "#1D4757"
}: CheatSheetProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationFrames = Math.round(scene.seconds * fps);

  const badgeSize = 88;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background,
        overflow: "hidden",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: width * 0.025
      }}
    >
      {[0, 1, 2].map((i) => {
        // Panels land one quarter of the scene apart, so the last lands mid-scene.
        const panelIn = spring({
          frame,
          fps,
          delay: Math.round((i * durationFrames) / 4),
          config: SPRING_CONFIG
        });
        return (
          <div
            key={i}
            style={{
              width: width * 0.27,
              height: height * 0.56,
              background: panelColor,
              borderRadius: 48,
              opacity: panelIn,
              transform: `translateY(${(1 - panelIn) * 70}px)`,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 28,
              padding: `0 ${width * 0.015}px`
            }}
          >
            <div
              style={{
                width: badgeSize,
                height: badgeSize,
                borderRadius: "50%",
                background: badgeColor,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 48,
                lineHeight: 1,
                fontWeight: 700,
                color: textColor,
                fontFamily: FONT_STACK
              }}
            >
              {i + 1}
            </div>
            <div
              style={{
                fontSize: 34,
                lineHeight: 1.3,
                fontWeight: 400,
                color: textColor,
                fontFamily: FONT_STACK,
                textAlign: "center"
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
