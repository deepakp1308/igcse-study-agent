import { describe, expect, it } from "vitest";

import type { RubricPart } from "../../types";
import { gradeNumeric, parseNumericAnswer } from "./numeric";

const mol: RubricPart = {
  id: "a",
  prompt: "Calc n.",
  answer_type: "numeric",
  max_marks: 3,
  numeric_answer: 0.25,
  numeric_unit: "mol",
  numeric_tolerance_pct: 2,
  accepted_phrasings: [],
  required_working_concepts: [],
  common_mistakes: [],
  model_answer_html: "<p>0.25 mol</p>",
  chapter_refs: [],
};

describe("parseNumericAnswer", () => {
  it("parses plain number", () => {
    expect(parseNumericAnswer("0.25")).toEqual({ value: 0.25, unit: null });
  });

  it("parses number + unit", () => {
    expect(parseNumericAnswer("0.25 mol")).toEqual({ value: 0.25, unit: "mol" });
  });

  it("parses scientific notation", () => {
    expect(parseNumericAnswer("2.5e-3")).toEqual({ value: 0.0025, unit: null });
  });

  it("rejects non-numeric", () => {
    expect(parseNumericAnswer("foo")).toEqual({ value: null, unit: null });
  });
});

describe("gradeNumeric", () => {
  it("within tolerance + correct unit = full match", () => {
    const r = gradeNumeric(mol, { text: "0.25 mol" });
    expect(r.within_tolerance).toBe(true);
    expect(r.unit_ok).toBe(true);
  });

  it("within tolerance but wrong unit = partial (unit_ok false)", () => {
    const r = gradeNumeric(mol, { text: "0.25 g" });
    expect(r.within_tolerance).toBe(true);
    expect(r.unit_ok).toBe(false);
  });

  it("outside tolerance fails", () => {
    const r = gradeNumeric(mol, { text: "1.0 mol" });
    expect(r.within_tolerance).toBe(false);
  });

  it("detects off-by-10 magnitude", () => {
    const r = gradeNumeric(mol, { text: "2.5 mol" });
    expect(r.within_tolerance).toBe(false);
    expect(r.off_by_magnitude).toBe(10);
  });

  it("accepts explicit numeric_value", () => {
    const r = gradeNumeric(mol, { value: 0.25, unit: "mol" });
    expect(r.within_tolerance).toBe(true);
    expect(r.unit_ok).toBe(true);
  });
});
