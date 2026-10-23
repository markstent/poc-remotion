export type SceneKind = "title" | "newsGrid" | "beforeAfter" | "framework" | "quote" | "analogy" | "cheatSheet" | "outro";

export interface StoryboardScene {
  id: string;
  kind: SceneKind;
  purpose: string;
  seconds: number;
  summary: string;
  on_screen: string[];
  source_ids: string[];
}

export interface Storyboard {
  objectives: string[];
  duration_seconds: number;
  rationale: string;
  scenes: StoryboardScene[];
}

export interface ScriptLine {
  scene_id: string;
  text: string;
  start_seconds: number | null;
  end_seconds: number | null;
}

export interface ScriptDoc {
  lines: ScriptLine[];
  on_screen: Record<string, string[]>;
}

/** One narration audio line; file is public-relative, e.g. audio/<hash>.wav. */
export interface NarrationLine {
  scene_id: string;
  text: string;
  start_seconds: number;
  end_seconds: number;
  file: string;
}
