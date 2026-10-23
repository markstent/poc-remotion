import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import { Colleague } from "../components/Colleague";
import type { SceneProps } from "./types";

export interface BeforeAfterProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  /** Narrow "before" prompt panel fill (pale blue). */
  beforeColor?: string;
  /** Wide "after" GCSE panel fill (white). */
  afterColor?: string;
  textColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";
const CHARACTER_SIZE_OF_HEIGHT = 0.48;

/** Before/after scene: Colleague oops beside a narrow prompt panel, then the wide GCSE panel. */
export function BeforeAfter({
  scene,
  fps,
  background = "#1D4757",
  beforeColor = "#CCFFFF",
  afterColor = "#FFFFFF",
  textColor = "#1D4757"
}: BeforeAfterProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationFrames = Math.round(scene.seconds * fps);

  // Duration-relative delays keep the reveal order deterministic at any length.
  const colleagueIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.02), config: SPRING_CONFIG });
  const beforeIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.05), config: SPRING_CONFIG });
  const afterIn = spring({ frame, fps, delay: Math.round(durationFrames * 0.2), config: SPRING_CONFIG });

  const panelHeight = height * 0.68;
  const characterSize = height * CHARACTER_SIZE_OF_HEIGHT;

  const panelLabel = {
    fontSize: 26,
    lineHeight: 1,
    fontWeight: 700,
    letterSpacing: 6,
    color: textColor,
    fontFamily: FONT_STACK,
    opacity: 0.6
  } as const;

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
        gap: width * 0.03,
        padding: `0 ${width * 0.04}px`
      }}
    >
      <div
        style={{
          opacity: colleagueIn,
          transform: `translateY(${(1 - colleagueIn) * 60}px)`,
          flexShrink: 0
        }}
      >
        <Colleague pose="oops" mood="oops" size={characterSize} />
      </div>
      <div
        style={{
          width: width * 0.24,
          height: panelHeight,
          background: beforeColor,
          borderRadius: 40,
          opacity: beforeIn,
          transform: `translateY(${(1 - beforeIn) * 70}px)`,
          padding: `${height * 0.05}px ${width * 0.02}px`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: height * 0.03
        }}
      >
        <div style={panelLabel}>BEFORE</div>
        <div
          style={{
            fontSize: 36,
            lineHeight: 1.3,
            fontWeight: 400,
            color: textColor,
            fontFamily: FONT_STACK,
            textAlign: "center",
            overflow: "hidden"
          }}
        >
          {scene.on_screen[0] ?? ""}
        </div>
      </div>
      <div
        style={{
          width: width * 0.38,
          height: panelHeight,
          background: afterColor,
          borderRadius: 40,
          opacity: afterIn,
          transform: `translateY(${(1 - afterIn) * 70}px)`,
          padding: `${height * 0.05}px ${width * 0.02}px`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: height * 0.03
        }}
      >
        <div style={panelLabel}>AFTER</div>
        <div
          style={{
            fontSize: 40,
            lineHeight: 1.3,
            fontWeight: 700,
            color: textColor,
            fontFamily: FONT_STACK,
            textAlign: "center",
            overflow: "hidden"
          }}
        >
          {scene.on_screen[1] ?? ""}
        </div>
      </div>
    </div>
  );
}
