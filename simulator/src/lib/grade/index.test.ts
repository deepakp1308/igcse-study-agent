import { describe, expect, it } from "vitest";

import type { QuestionRubric } from "../../types";
import { gradeQuestion } from "./index";

const numericQuestion: QuestionRubric = {
  question_id: "q1",
  source_question_db_id: 1,
  type: "numeric",
  max_marks: 3,
  stem: "Calculate the moles in 10 g of calcium.",
  figure_paths: [],
  parts: [
    {
      id: "a",
      prompt: "Calculate n.",
      answer_type: "numeric",
      max_marks: 3,
      numeric_answer: 0.25,
      numeric_unit: "mol",
      numeric_tolerance_pct: 2,
      accepted_phrasings: [],
      required_working_concepts: [
        { concept: "uses n = m/M", marks: 1, hints: ["n = m/M"] },
        { concept: "correct molar mass", marks: 1, hints: ["40"] },
      ],
      common_mistakes: [
        {
          match: { kind: "keyword_absent", keyword: "mol" },
          feedback: "Remember the unit.",
        },
        {
          match: { kind: "numeric_off_by", magnitude: 10 },
          feedback: "Check your decimal place.",
        },
      ],
      model_answer_html: "<p>0.25 mol</p>",
      chapter_refs: ["n = m/M"],
    },
  ],
};

describe("gradeQuestion (numeric with working)", () => {
  it("full marks when working + answer correct", async () => {
    const g = await gradeQuestion(numericQuestion, {
      a: {
        part_id: "a",
        text: "n = m/M = 10 / 40 = 0.25 mol",
      },
    });
    expect(g.verdict).toBe("correct");
    expect(g.marks_awarded).toBe(3);
  });

  it("partial marks if no working shown", async () => {
    const g = await gradeQuestion(numericQuestion, {
      a: { part_id: "a", text: "0.25 mol" },
    });
    expect(g.verdict).toBe("partial");
    expect(g.marks_awarded).toBeGreaterThan(0);
    expect(g.marks_awarded).toBeLessThan(3);
  });

  it("triggers off-by-10 feedback", async () => {
    const g = await gradeQuestion(numericQuestion, {
      a: { part_id: "a", text: "2.5 mol" },
    });
    const pg = g.parts[0];
    const kinds = pg.triggered_mistakes.map((m) => m.match.kind);
    expect(kinds).toContain("numeric_off_by");
  });

  it("triggers missing unit feedback", async () => {
    const g = await gradeQuestion(numericQuestion, {
      a: { part_id: "a", text: "0.25" },
    });
    const kinds = g.parts[0].triggered_mistakes.map((m) => m.match.kind);
    expect(kinds).toContain("keyword_absent");
  });
});
