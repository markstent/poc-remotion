import type { StoryboardScene } from "../lib/types";

/**
 * Canonical shared props for every scene component. The registry imports this
 * type; scene files either import it from here or declare an identical local
 * shape so scene files stay self-contained. The parent composition wraps each
 * scene in a <Sequence> lasting `scene.seconds * fps` frames.
 */
export type SceneProps = {
  scene: StoryboardScene;
  fps: number;
};
