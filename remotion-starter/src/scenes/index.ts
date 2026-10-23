import type { FC } from "react";
import type { SceneKind } from "../lib/types";
import { Analogy } from "./Analogy";
import { BeforeAfter } from "./BeforeAfter";
import { CheatSheet } from "./CheatSheet";
import { Framework } from "./Framework";
import { NewsGrid } from "./NewsGrid";
import { Outro } from "./Outro";
import { Quote } from "./Quote";
import { Title } from "./Title";
import type { SceneProps } from "./types";

/**
 * Registry of every scene kind. `Record` over the SceneKind union makes
 * completeness a compile error: adding a kind to types.ts without adding a
 * component here fails `tsc`.
 */
export const SCENES: Record<SceneKind, FC<SceneProps>> = {
  title: Title,
  newsGrid: NewsGrid,
  beforeAfter: BeforeAfter,
  framework: Framework,
  quote: Quote,
  analogy: Analogy,
  cheatSheet: CheatSheet,
  outro: Outro
};
