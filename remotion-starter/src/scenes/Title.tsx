import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { JSX } from "react";
import { Colleague } from "../components/Colleague";
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

export interface TitleProps extends SceneProps {
  /** Brand colours as props with token defaults; this component never reads tokens itself. */
  background?: string;
  titleColor?: string;
  accentColor?: string;
}

const SPRING_CONFIG = { damping: 14, stiffness: 110, mass: 0.7 };
const FONT_STACK = "Helvetica, Arial, sans-serif";
const CHARACTER_SIZE = 440;
const BAR_WIDTH = 560;
const BAR_HEIGHT = 22;

/** Title scene: Colleague enters from the right, two-line kinetic title, lime underline bar. */
export function Title({
  scene,
  fps,
  background = "#CCFFFF",
  titleColor = "#1D4757",
  accentColor = "#C4F600"
}: TitleProps): JSX.Element {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  const line1 = scene.on_screen[0] ?? "";
  const line2 = scene.on_screen[1] ?? "";

  // Fixed delays keep the reveal order deterministic for any scene length.
  const line1In = spring({ frame, fps, delay: 2, config: SPRING_CONFIG });
  const line2In = spring({ frame, fps, delay: 10, config: SPRING_CONFIG });
  const barIn = spring({ frame, fps, delay: 20, config: SPRING_CONFIG });
  const characterIn = spring({
    frame,
    fps,
    delay: 4,
    config: { damping: 12, stiffness: 70, mass: 0.9 }
  });

  // Masked slide-up for each title line, drawn from its own spring.
  const line1Rise = (1 - line1In) * 110;
  const line2Rise = (1 - line2In) * 110;

  const characterRestX = width - CHARACTER_SIZE * 0.92;
  const characterX = interpolate(characterIn, [0, 1], [width + CHARACTER_SIZE, characterRestX]);

  return (
    <div style={{ position: "absolute", inset: 0, background, overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          left: width * 0.08,
          top: height * 0.5,
          transform: "translateY(-50%)",
          maxWidth: width * 0.56
        }}
      >
        <div style={{ overflow: "hidden" }}>
          <div
            style={{
              fontSize: 108,
              lineHeight: 1.05,
              fontWeight: 700,
              color: titleColor,
              fontFamily: FONT_STACK,
              opacity: line1In,
              transform: `translateY(${line1Rise}px)`
            }}
          >
            {line1}
          </div>
        </div>
        <div style={{ overflow: "hidden" }}>
          <div
            style={{
              fontSize: 108,
              lineHeight: 1.05,
              fontWeight: 700,
              color: titleColor,
              fontFamily: FONT_STACK,
              opacity: line2In,
              transform: `translateY(${line2Rise}px)`
            }}
          >
            {line2}
          </div>
        </div>
        <div
          style={{
            width: BAR_WIDTH,
            height: BAR_HEIGHT,
            marginTop: 34,
            background: accentColor,
            transformOrigin: "left center",
            transform: `scaleX(${barIn})`
          }}
        />
      </div>
      <div style={{ position: "absolute", left: characterX, bottom: height * 0.1 }}>
        <Colleague pose="idle" size={CHARACTER_SIZE} />
      </div>
    </div>
  );
}
