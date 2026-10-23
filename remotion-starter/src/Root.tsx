import { Composition } from "remotion";
import { MyComposition } from "./Composition";
import {
  DEFAULT_TRAINER_VIDEO_PROPS,
  TRAINER_VIDEO_FPS,
  TrainerVideo,
  calculateTrainerVideoMetadata,
  trainerVideoDurationInFrames
} from "./TrainerVideo";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <MyComposition />
      <Composition
        id="TrainerVideo"
        component={TrainerVideo}
        durationInFrames={trainerVideoDurationInFrames(DEFAULT_TRAINER_VIDEO_PROPS.storyboard)}
        fps={TRAINER_VIDEO_FPS}
        width={1920}
        height={1080}
        defaultProps={DEFAULT_TRAINER_VIDEO_PROPS}
        calculateMetadata={calculateTrainerVideoMetadata}
      />
    </>
  );
};
