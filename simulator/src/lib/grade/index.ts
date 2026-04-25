import type {
  MistakePattern,
  PartGrade,
  QuestionGrade,
  QuestionRubric,
  RubricPart,
  StudentAnswer,
  Verdict,
} from "../../types";
import { scoreConcepts, conceptsToMarks, type EmbeddingsFn } from "./concepts";
import { gradeMCQ } from "./mcq";
import { detectMistakes } from "./mistakes";
import { gradeNumeric, parseNumericAnswer, type NumericResult } from "./numeric";

function verdictFor(awarded: number, max: number, isSelfCheck: boolean): Verdict {
  if (isSelfCheck) return "self_check";
  if (max === 0) return "correct";
  if (awarded >= max - 1e-6) return "correct";
  if (awarded > 0) return "partial";
  return "incorrect";
}

function shortTextMatch(part: RubricPart, text: string): boolean {
  if (!text) return false;
  const n = text.toLowerCase().trim();
  return part.accepted_phrasings.some((p) => {
    const pp = p.toLowerCase().trim();
    if (!pp) return false;
    return n.includes(pp) || pp.includes(n);
  });
}

export async function gradePart(
  part: RubricPart,
  answer: StudentAnswer,
  embeddingsFn?: EmbeddingsFn,
): Promise<PartGrade> {
  let awarded = 0;
  const max = part.max_marks;
  const concepts = [...part.required_working_concepts];
  let triggered: MistakePattern[] = [];
  let numericResult: NumericResult | null = null;

  switch (part.answer_type) {
    case "mcq": {
      const r = gradeMCQ(part, answer.mcq_label);
      awarded = r.correct ? max : 0;
      break;
    }
    case "numeric": {
      numericResult = gradeNumeric(part, {
        value: answer.numeric_value,
        unit: answer.numeric_unit,
        text: answer.text,
      });
      const conceptResults = await scoreConcepts(
        answer.text ?? "",
        concepts,
        embeddingsFn,
      );
      const { awarded: conceptAwarded, max: conceptMax } = conceptsToMarks(conceptResults);
      const remainingForFinal = Math.max(0, max - conceptMax);
      const finalBonus = numericResult.within_tolerance
        ? remainingForFinal * (numericResult.unit_ok ? 1 : 0.5)
        : 0;
      awarded = conceptAwarded + finalBonus;
      triggered = detectMistakes(part, answer.text ?? "", numericResult);
      return {
        part_id: part.id,
        verdict: verdictFor(awarded, max, false),
        marks_awarded: Math.min(max, Math.round(awarded * 2) / 2),
        max_marks: max,
        concepts: conceptResults,
        triggered_mistakes: triggered,
        model_answer_html: part.model_answer_html,
        chapter_refs: part.chapter_refs,
      };
    }
    case "short_text": {
      if (shortTextMatch(part, answer.text ?? "")) {
        awarded = max;
      } else {
        const conceptResults = await scoreConcepts(
          answer.text ?? "",
          concepts,
          embeddingsFn,
        );
        awarded = conceptsToMarks(conceptResults).awarded;
        triggered = detectMistakes(part, answer.text ?? "", null);
        return {
          part_id: part.id,
          verdict: verdictFor(awarded, max, false),
          marks_awarded: Math.min(max, awarded),
          max_marks: max,
          concepts: conceptResults,
          triggered_mistakes: triggered,
          model_answer_html: part.model_answer_html,
          chapter_refs: part.chapter_refs,
        };
      }
      break;
    }
    case "free_text": {
      const conceptResults = await scoreConcepts(
        answer.text ?? "",
        concepts,
        embeddingsFn,
      );
      awarded = conceptsToMarks(conceptResults).awarded;
      triggered = detectMistakes(part, answer.text ?? "", null);
      return {
        part_id: part.id,
        verdict: verdictFor(awarded, max, false),
        marks_awarded: Math.min(max, awarded),
        max_marks: max,
        concepts: conceptResults,
        triggered_mistakes: triggered,
        model_answer_html: part.model_answer_html,
        chapter_refs: part.chapter_refs,
      };
    }
    case "self_check": {
      const ticked = new Set(answer.self_check_concepts ?? []);
      const conceptResults = concepts.map((c) => ({
        concept: c.concept,
        marks: c.marks,
        awarded: ticked.has(c.concept) ? c.marks : 0,
        hit: ticked.has(c.concept),
      }));
      awarded = conceptResults.reduce((s, c) => s + c.awarded, 0);
      return {
        part_id: part.id,
        verdict: "self_check",
        marks_awarded: Math.min(max, awarded),
        max_marks: max,
        concepts: conceptResults,
        triggered_mistakes: [],
        model_answer_html: part.model_answer_html,
        chapter_refs: part.chapter_refs,
      };
    }
  }

  return {
    part_id: part.id,
    verdict: verdictFor(awarded, max, false),
    marks_awarded: Math.min(max, awarded),
    max_marks: max,
    concepts: [],
    triggered_mistakes: triggered,
    model_answer_html: part.model_answer_html,
    chapter_refs: part.chapter_refs,
  };
}

export async function gradeQuestion(
  rubric: QuestionRubric,
  answers: Record<string, StudentAnswer>,
  embeddingsFn?: EmbeddingsFn,
): Promise<QuestionGrade> {
  const parts: PartGrade[] = [];
  for (const part of rubric.parts) {
    const answer = answers[part.id] ?? { part_id: part.id };
    parts.push(await gradePart(part, answer, embeddingsFn));
  }
  const awarded = parts.reduce((s, p) => s + p.marks_awarded, 0);
  const max = rubric.max_marks;
  const hasSelfCheck = parts.some((p) => p.verdict === "self_check");
  const verdict: Verdict = hasSelfCheck
    ? "self_check"
    : awarded >= max - 1e-6
      ? "correct"
      : awarded > 0
        ? "partial"
        : "incorrect";
  return {
    question_id: rubric.question_id,
    verdict,
    marks_awarded: Math.round(awarded * 2) / 2,
    max_marks: max,
    parts,
  };
}

export { parseNumericAnswer };
export type { NumericResult };
