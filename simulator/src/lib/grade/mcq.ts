import type { RubricPart } from "../../types";

export interface MCQResult {
  correct: boolean;
  correct_label: string | null;
  student_label: string | null;
}

export function gradeMCQ(part: RubricPart, studentLabel: string | null | undefined): MCQResult {
  const correctLabel = part.mcq_correct_label ?? null;
  const norm = studentLabel ? studentLabel.trim().toUpperCase() : null;
  const correct = Boolean(correctLabel && norm && correctLabel.toUpperCase() === norm);
  return { correct, correct_label: correctLabel, student_label: norm };
}
