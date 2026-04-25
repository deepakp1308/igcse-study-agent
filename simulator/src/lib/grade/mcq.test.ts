import { describe, expect, it } from "vitest";

import type { RubricPart } from "../../types";
import { gradeMCQ } from "./mcq";

const base: RubricPart = {
  id: "a",
  prompt: "Pick.",
  answer_type: "mcq",
  max_marks: 1,
  mcq_options: [
    { label: "A", text: "x" },
    { label: "B", text: "y" },
  ],
  mcq_correct_label: "B",
  accepted_phrasings: [],
  required_working_concepts: [],
  common_mistakes: [],
  model_answer_html: "<p>B</p>",
  chapter_refs: [],
};

describe("gradeMCQ", () => {
  it("marks correct letter", () => {
    expect(gradeMCQ(base, "B").correct).toBe(true);
  });

  it("marks incorrect letter", () => {
    expect(gradeMCQ(base, "A").correct).toBe(false);
  });

  it("is case-insensitive and trims whitespace", () => {
    expect(gradeMCQ(base, "  b ").correct).toBe(true);
  });

  it("returns incorrect for null", () => {
    expect(gradeMCQ(base, null).correct).toBe(false);
  });
});
