// Aggregated Russian dictionary. Each module contributes { uzbekKey: russianText }.
// Later spreads win on key collisions, but duplicates should map to the same value.

import { ru as common } from "./common";
import { ru as group1 } from "./group1";
import { ru as group2 } from "./group2";
import { ru as group3 } from "./group3";
import { ru as group4 } from "./group4";
import { ru as group5 } from "./group5";
import { ru as group6 } from "./group6";

export const ru: Record<string, string> = {
  ...common,
  ...group1,
  ...group2,
  ...group3,
  ...group4,
  ...group5,
  ...group6,
};
