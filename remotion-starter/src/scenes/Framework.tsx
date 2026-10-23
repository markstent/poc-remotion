import { spring, useCurrentFrame, useVideoConfig } from "remotion";
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

export interface FrameworkProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  letterColor?: string;
  /** Panel fills in reveal order: G turquoise, C paleBlue, S paleBlue, E lime. */
  panelColors?: [string, string, string, string];
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";
const PANEL_LETTERS = ["G", "C", "S", "E"] as const;
const DEFAULT_PANEL_COLORS: [string, string, string, string] = [
  "#27E2CC",
  "#CCFFFF",
  "#CCFFFF",
  "#C4F600"
];

/** Framework scene: four rounded panels revealed in order across the duration. */
export function Framework({
  scene,
  fps,
  background = "#1D4757",
  letterColor = "#1D4757",
  panelColors = DEFAULT_PANEL_COLORS
}: FrameworkProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationFrames = Math.round(scene.seconds * fps);

  // Panels enter one fifth of the scene apart, so the last lands mid-scene.
  const stagger = durationFrames / 5;

  const panelWidth = width * 0.17;
  const panelHeight = height * 0.52;
  const gap = width * 0.024;
  const startX = (width - (panelWidth * 4 + gap * 3)) / 2;
  const top = (height - panelHeight) / 2;

  return (
    <div style={{ position: "absolute", inset: 0, background, overflow: "hidden" }}>
      {PANEL_LETTERS.map((letter, i) => {
        const panelIn = spring({
          frame,
          fps,
          delay: Math.round(i * stagger),
          config: SPRING_CONFIG
        });
        const caption = scene.on_screen[i] ?? "";
        return (
          <div
            key={letter}
            style={{
              position: "absolute",
              left: startX + i * (panelWidth + gap),
              top: top + (1 - panelIn) * 70,
              width: panelWidth,
              height: panelHeight,
              background: panelColors[i],
              borderRadius: 48,
              opacity: panelIn,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 20,
              fontFamily: FONT_STACK
            }}
          >
            <div style={{ fontSize: 190, lineHeight: 1, fontWeight: 700, color: letterColor }}>
              {letter}
            </div>
            {caption ? (
              <div
                style={{
                  fontSize: 34,
                  lineHeight: 1.2,
                  fontWeight: 400,
                  color: letterColor,
                  textAlign: "center",
                  padding: "0 24px"
                }}
              >
                {caption}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
