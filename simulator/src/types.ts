// Shapes mirror the Python pydantic schemas in agent/store/schemas.py.
// If you change the Python schema, update this file too (or generate from it).

export type QuestionType = "mcq" | "short" | "long" | "structured" | "numeric";

export type AnswerType = "mcq" | "numeric" | "short_text" | "free_text" | "self_check";

export interface MCQOption {
  label: string;
  text: string;
}

export interface RequiredConcept {
  concept: string;
  marks: number;
  hints: string[];
}

export type MistakeKind =
  | "formula_inverted"
  | "keyword_absent"
  | "keyword_present"
  | "numeric_off_by";

export interface MistakeMatch {
  kind: MistakeKind;
  keyword?: string | null;
  magnitude?: number | null;
}

export interface MistakePattern {
  match: MistakeMatch;
  feedback: string;
}

export interface RubricPart {
  id: string;
  prompt: string;
  answer_type: AnswerType;
  max_marks: number;
  mcq_options?: MCQOption[] | null;
  mcq_correct_label?: string | null;
  numeric_answer?: number | null;
  numeric_unit?: string | null;
  numeric_tolerance_pct?: number | null;
  accepted_phrasings: string[];
  required_working_concepts: RequiredConcept[];
  common_mistakes: MistakePattern[];
  model_answer_html: string;
  chapter_refs: string[];
}

export interface QuestionRubric {
  question_id: string;
  source_question_db_id: number;
  type: QuestionType;
  max_marks: number;
  stem: string;
  figure_paths: string[];
  parts: RubricPart[];
}

export interface SimulatorSet {
  subject: string;
  chapter: string;
  generated_at: string;
  questions: QuestionRubric[];
  topic_index: Record<string, string[]>;
}

export interface SetsIndex {
  sets: Array<{
    file: string;
    subject: string;
    chapter: string;
    question_count: number;
    generated_at: string;
  }>;
}

// Runtime grading artifacts

export type Verdict = "correct" | "partial" | "incorrect" | "self_check";

export interface ConceptResult {
  concept: string;
  marks: number;
  awarded: number;
  hit: boolean;
}

export interface PartGrade {
  part_id: string;
  verdict: Verdict;
  marks_awarded: number;
  max_marks: number;
  concepts: ConceptResult[];
  triggered_mistakes: MistakePattern[];
  model_answer_html: string;
  chapter_refs: string[];
}

export interface QuestionGrade {
  question_id: string;
  verdict: Verdict;
  marks_awarded: number;
  max_marks: number;
  parts: PartGrade[];
}

export interface StudentAnswer {
  part_id: string;
  mcq_label?: string | null;
  numeric_value?: number | null;
  numeric_unit?: string | null;
  text?: string | null;
  self_check_concepts?: string[];
}
