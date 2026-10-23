import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import { Colleague } from "../components/Colleague";
import type { SceneProps } from "./types";

export interface OutroProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  cardColor?: string;
  accentColor?: string;
  textColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";

/** Outro scene: white prompt card pops in, Colleague cheers beside it with a wave. */
export function Outro({
  scene,
  fps,
  background = "#1D4757",
  cardColor = "#FFFFFF",
  accentColor = "#C4F600",
  textColor = "#1D4757"
}: OutroProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationFrames = Math.round(scene.seconds * fps);

  const cardIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.03), config: SPRING_CONFIG });
  const characterIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.12), config: SPRING_CONFIG });

  const characterSize = height * 0.55;
  // Deterministic wave: a fixed-rate sine after the character settles in.
  const wave = Math.sin(frame * 0.18) * 5 * characterIn;

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
        gap: width * 0.04
      }}
    >
      <div
        style={{
          width: width * 0.42,
          background: cardColor,
          borderRadius: 48,
          padding: `${height * 0.06}px ${width * 0.03}px`,
          textAlign: "center",
          opacity: cardIn,
          transform: `scale(${0.8 + 0.2 * cardIn})`
        }}
      >
        <div
          style={{
            fontSize: 56,
            lineHeight: 1.2,
            fontWeight: 700,
            color: textColor,
            fontFamily: FONT_STACK
          }}
        >
          {scene.on_screen[0] ?? ""}
        </div>
        <div
          style={{
            width: 220,
            height: 20,
            margin: `${height * 0.03}px auto 0`,
            background: accentColor,
            transformOrigin: "center",
            transform: `scaleX(${cardIn})`
          }}
        />
      </div>
      <div
        style={{
          opacity: characterIn,
          transform: `translateX(${(1 - characterIn) * 120}px) rotate(${wave}deg)`,
          transformOrigin: "50% 85%",
          flexShrink: 0
        }}
      >
        <Colleague pose="cheer" size={characterSize} />
      </div>
    </div>
  );
}
