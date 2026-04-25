import type { MistakePattern, RubricPart } from "../../types";
import type { NumericResult } from "./numeric";

/**
 * Detect triggered common-mistake patterns given the student's raw answer
 * and (optionally) the numeric grading result for numeric parts.
 */

function hasKeyword(text: string, keyword: string): boolean {
  if (!keyword) return false;
  return text.toLowerCase().includes(keyword.toLowerCase());
}

export function detectMistakes(
  part: RubricPart,
  studentText: string,
  numeric?: NumericResult | null,
): MistakePattern[] {
  const triggered: MistakePattern[] = [];
  const text = studentText ?? "";
  for (const m of part.common_mistakes) {
    switch (m.match.kind) {
      case "formula_inverted": {
        // Heuristic: if the expected answer is numeric and the student's answer
        // is the reciprocal of the expected within tolerance, call it an inversion.
        if (numeric && numeric.parsed != null && numeric.expected != null && numeric.expected !== 0) {
          const inv = 1 / numeric.expected;
          const tol = Math.abs(inv) * 0.05 || 1e-9;
          if (Math.abs(numeric.parsed - inv) <= tol) triggered.push(m);
        } else if (part.numeric_answer != null && numeric?.parsed != null) {
          const inv = 1 / part.numeric_answer;
          const tol = Math.abs(inv) * 0.05 || 1e-9;
          if (Math.abs(numeric.parsed - inv) <= tol) triggered.push(m);
        }
        break;
      }
      case "keyword_absent": {
        if (m.match.keyword && !hasKeyword(text, m.match.keyword)) triggered.push(m);
        break;
      }
      case "keyword_present": {
        if (m.match.keyword && hasKeyword(text, m.match.keyword)) triggered.push(m);
        break;
      }
      case "numeric_off_by": {
        if (
          numeric?.off_by_magnitude != null &&
          m.match.magnitude != null &&
          Math.abs(numeric.off_by_magnitude - m.match.magnitude) < 1e-6
        ) {
          triggered.push(m);
        }
        break;
      }
    }
  }
  return triggered;
}
