import type { JSX } from "react";
import {
  Audio,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  type CalculateMetadataFunction
} from "remotion";
import type {
  NarrationLine,
  ScriptDoc,
  ScriptLine,
  Storyboard,
  StoryboardScene
} from "./lib/types";
import { SCENES } from "./scenes";
import fixtureScript from "../testdata/fixture-script.json";
import fixtureStoryboard from "../testdata/fixture-storyboard.json";

/**
 * Props for the assembled training video. Brand colours are props with token
 * defaults; this component never reads tokens itself (ruling R8). Declared as
 * a type alias so Remotion's `Record<string, unknown>` constraint is met.
 */
export type TrainerVideoProps = {
  storyboard: Storyboard;
  script: ScriptDoc;
  /** Narration audio lines; absent when the project has no narration. */
  narration?: { lines: NarrationLine[] };
  /** Caption pill panel colour; default is translucent darkTeal. */
  captionBackground?: string;
  /** Caption cue bar colour; default is lime. */
  cueColor?: string;
  /** Caption text colour; default is white. */
  captionColor?: string;
};

const FONT_STACK = "Helvetica, Arial, sans-serif";
/** Fixed composition frame rate; the duration formula below is pinned to it. */
export const TRAINER_VIDEO_FPS = 30;
/** Silent tail after the last scene so closing animations can settle. */
const TRAILING_PAD_SECONDS = 0.5;

/** Total timeline length: ceil((sum of scene seconds + pad) * fps). */
export function trainerVideoDurationInFrames(storyboard: Storyboard): number {
  const totalSeconds = storyboard.scenes.reduce((sum, scene) => sum + scene.seconds, 0);
  return Math.ceil((totalSeconds + TRAILING_PAD_SECONDS) * TRAINER_VIDEO_FPS);
}

export const calculateTrainerVideoMetadata: CalculateMetadataFunction<TrainerVideoProps> = ({
  props
}) => {
  return { durationInFrames: trainerVideoDurationInFrames(props.storyboard) };
};

/** Start and end time in seconds of each scene on the global timeline. */
function sceneWindows(storyboard: Storyboard): Map<string, { start: number; end: number }> {
  const windows = new Map<string, { start: number; end: number }>();
  let cursor = 0;
  for (const scene of storyboard.scenes) {
    windows.set(scene.id, { start: cursor, end: cursor + scene.seconds });
    cursor += scene.seconds;
  }
  return windows;
}

/** Representative time used to rank lines whose own timings are null. */
function lineAnchorTime(
  line: ScriptLine,
  windows: Map<string, { start: number; end: number }>
): number {
  if (line.start_seconds !== null && line.end_seconds !== null) {
    return (line.start_seconds + line.end_seconds) / 2;
  }
  if (line.start_seconds !== null) {
    return line.start_seconds;
  }
  if (line.end_seconds !== null) {
    return line.end_seconds;
  }
  const window = windows.get(line.scene_id);
  if (!window) {
    return 0;
  }
  return (window.start + window.end) / 2;
}

/**
 * The caption to show at `timeSeconds`. Lines with full timings win via
 * `start_seconds <= t < end_seconds`; between such windows nothing shows.
 * When a line's timings are null it can never win the timed search, so such
 * lines fall back to the nearest anchor time (ties keep the earlier line).
 */
export function activeCaptionLine(
  script: ScriptDoc,
  storyboard: Storyboard,
  timeSeconds: number
): ScriptLine | null {
  const timed = script.lines.find(
    (line) =>
      line.start_seconds !== null &&
      line.end_seconds !== null &&
      line.start_seconds <= timeSeconds &&
      timeSeconds < line.end_seconds
  );
  if (timed) {
    return timed;
  }
  const untimed = script.lines.filter(
    (line) => line.start_seconds === null || line.end_seconds === null
  );
  if (untimed.length === 0) {
    return null;
  }
  const windows = sceneWindows(storyboard);
  let nearest = untimed[0];
  for (const candidate of untimed) {
    if (
      Math.abs(lineAnchorTime(candidate, windows) - timeSeconds) <
      Math.abs(lineAnchorTime(nearest, windows) - timeSeconds)
    ) {
      nearest = candidate;
    }
  }
  return nearest;
}

/** Assembled video: one <Sequence> per scene plus a burned-in caption pill. */
export function TrainerVideo({
  storyboard,
  script,
  narration,
  captionBackground = "rgba(29, 71, 87, 0.85)",
  cueColor = "#C4F600",
  captionColor = "#FFFFFF"
}: TrainerVideoProps): JSX.Element {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // Scene offsets accumulate in seconds and round once per scene, so integer
  // frame boundaries stay drift-free for whole-second scenes.
  let cursorSeconds = 0;
  const placed: { scene: StoryboardScene; from: number; durationInFrames: number }[] =
    storyboard.scenes.map((scene) => {
      const from = Math.round(cursorSeconds * fps);
      cursorSeconds += scene.seconds;
      return { scene, from, durationInFrames: Math.round(scene.seconds * fps) };
    });

  const caption = activeCaptionLine(script, storyboard, frame / fps);

  return (
    <div style={{ position: "absolute", inset: 0, background: "#FFFFFF" }}>
      {placed.map(({ scene, from, durationInFrames }) => {
        const SceneComponent = SCENES[scene.kind];
        return (
          <Sequence key={scene.id} from={from} durationInFrames={durationInFrames} name={scene.id}>
            <SceneComponent scene={scene} fps={fps} />
          </Sequence>
        );
      })}
      {narration?.lines.map((line) => (
        <Sequence
          key={`${line.file}-${line.start_seconds}`}
          from={Math.round(line.start_seconds * fps)}
        >
          <Audio src={staticFile(line.file)} />
        </Sequence>
      ))}
      {caption === null ? null : (
        <div
          style={{
            position: "absolute",
            left: width * 0.06,
            bottom: height * 0.07,
            zIndex: 10,
            display: "flex",
            alignItems: "stretch",
            background: captionBackground,
            borderRadius: 18,
            overflow: "hidden",
            maxWidth: width * 0.7
          }}
        >
          <div style={{ width: 12, flexShrink: 0, background: cueColor }} />
          <div
            style={{
              padding: "26px 40px",
              color: captionColor,
              fontFamily: FONT_STACK,
              fontWeight: 600,
              fontSize: 46,
              lineHeight: 1.3
            }}
          >
            {caption.text}
          </div>
        </div>
      )}
    </div>
  );
}

/** defaultProps so stills and renders work without --props (ruling R4). */
export const DEFAULT_TRAINER_VIDEO_PROPS: TrainerVideoProps = {
  storyboard: fixtureStoryboard as Storyboard,
  script: fixtureScript as ScriptDoc
};
