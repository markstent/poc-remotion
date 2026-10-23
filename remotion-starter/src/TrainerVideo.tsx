import type { JSX } from "react";
import {
  Audio,
  Sequence,
  staticFile,
  useVideoConfig,
  type CalculateMetadataFunction
} from "remotion";
import type { NarrationLine, ScriptDoc, Storyboard, StoryboardScene } from "./lib/types";
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
};

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

/**
 * Assembled video: one <Sequence> per scene plus the narration audio.
 * Captions are deliberately not burned in (user decision on video 1): the
 * SRT sidecar carries them so players can toggle subtitles instead.
 */
export function TrainerVideo({ storyboard, script, narration }: TrainerVideoProps): JSX.Element {
  const { fps } = useVideoConfig();

  // Scene offsets accumulate in seconds and round once per scene, so integer
  // frame boundaries stay drift-free for whole-second scenes.
  let cursorSeconds = 0;
  const placed: { scene: StoryboardScene; from: number; durationInFrames: number }[] =
    storyboard.scenes.map((scene) => {
      const from = Math.round(cursorSeconds * fps);
      cursorSeconds += scene.seconds;
      return { scene, from, durationInFrames: Math.round(scene.seconds * fps) };
    });

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
      {narration?.lines.map((line, i) => (
        <Sequence
          key={`${line.file}-${line.start_seconds}-${i}`}
          from={Math.round(line.start_seconds * fps)}
        >
          <Audio src={staticFile(line.file)} />
        </Sequence>
      ))}
    </div>
  );
}

/** defaultProps so stills and renders work without --props (ruling R4). */
export const DEFAULT_TRAINER_VIDEO_PROPS: TrainerVideoProps = {
  storyboard: fixtureStoryboard as Storyboard,
  script: fixtureScript as ScriptDoc
};
