"""Pydantic schemas for every JSON blob the Cursor agent produces.

Every schema below is the contract for a specific agent step in ``AGENT_SOP.md``.
The CLI ``save-*`` subcommands validate stdin JSON against these schemas before
any write to SQLite. Validation failures are routed to ``review_queue``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionType(StrEnum):
    MCQ = "mcq"
    SHORT = "short"
    LONG = "long"
    STRUCTURED = "structured"
    NUMERIC = "numeric"


class Fit(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class BoundingBox(BaseModel):
    """Normalized bbox (0..1) on the rendered page PNG, origin top-left."""

    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class MCQOption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=4)
    text: str


class SubPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=8)
    prompt: str
    marks: int = Field(ge=0, le=50)
    type: QuestionType = QuestionType.SHORT


class ExtractedQuestion(BaseModel):
    """One question extracted from a past-paper page.

    The agent may emit multiple questions per page. Sub-parts of a single
    question (a, b, c, i, ii) are captured in ``sub_parts`` rather than as
    separate top-level questions.
    """

    model_config = ConfigDict(extra="forbid")

    number: str = Field(description="Question number as printed, e.g. '1', '12', 'Section B Q3'.")
    type: QuestionType
    marks: int = Field(ge=0, le=50)
    stem: str = Field(min_length=1)
    sub_parts: list[SubPart] = Field(default_factory=list)
    options: list[MCQOption] | None = None
    figure_bboxes: list[BoundingBox] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None

    @field_validator("options")
    @classmethod
    def _mcq_options_non_empty(
        cls, v: list[MCQOption] | None
    ) -> list[MCQOption] | None:
        if v is not None and len(v) < 2:
            raise ValueError("MCQ must have at least 2 options")
        return v


class PaperMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str
    year: int | None = None
    session: str | None = None
    paper_number: str | None = None
    tier: Literal["core", "extended", "foundation", "higher", "unknown"] = "unknown"
    total_marks: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class PageExtraction(BaseModel):
    """Agent output for a single rendered page."""

    model_config = ConfigDict(extra="forbid")
    paper_id: int
    page_idx: int = Field(ge=0)
    questions: list[ExtractedQuestion] = Field(default_factory=list)


class ChapterTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    summary: str
    key_terms: list[str] = Field(default_factory=list)


class WorkedExample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    solution: str


class ChapterProfile(BaseModel):
    """Structured summary of everything taught in a chapter."""

    model_config = ConfigDict(extra="forbid")
    subject: str
    chapter_name: str
    syllabus_topics: list[ChapterTopic]
    definitions: list[str] = Field(default_factory=list)
    formulas: list[str] = Field(default_factory=list)
    worked_examples: list[WorkedExample] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)
    out_of_scope_notes: list[str] = Field(default_factory=list)


class MatchDecision(BaseModel):
    """Agent judgment for a single (chapter, question) candidate."""

    model_config = ConfigDict(extra="forbid")
    chapter_id: int
    question_id: int
    fit: Fit
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    missing_concepts: list[str] = Field(default_factory=list)


class SolverStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int = Field(ge=1)
    explanation: str
    chapter_ref: str | None = None


class SolverOutput(BaseModel):
    """Agent solver's structured answer for a question."""

    model_config = ConfigDict(extra="forbid")
    question_id: int
    chapter_id: int
    out_of_scope: bool = False
    missing: list[str] = Field(default_factory=list)
    final_answer: str | None = None
    steps: list[SolverStep] = Field(default_factory=list)
    chapter_refs: list[str] = Field(default_factory=list)


class CriticOutput(BaseModel):
    """Independent critic's re-grading of the solver."""

    model_config = ConfigDict(extra="forbid")
    question_id: int
    chapter_id: int
    agrees: bool
    final_answer: str | None = None
    issues: list[str] = Field(default_factory=list)
    chapter_alignment_ok: bool = True


class MistakeMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["formula_inverted", "keyword_absent", "keyword_present", "numeric_off_by"]
    keyword: str | None = None
    magnitude: float | None = None


class MistakePattern(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: MistakeMatch
    feedback: str


class RequiredConcept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concept: str
    marks: int = Field(ge=0)
    hints: list[str] = Field(default_factory=list, description="Phrases that indicate concept presence")


class RubricPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    prompt: str
    answer_type: Literal["mcq", "numeric", "short_text", "free_text", "self_check"]
    max_marks: int = Field(ge=0)
    mcq_options: list[MCQOption] | None = None
    mcq_correct_label: str | None = None
    numeric_answer: float | None = None
    numeric_unit: str | None = None
    numeric_tolerance_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    accepted_phrasings: list[str] = Field(default_factory=list)
    required_working_concepts: list[RequiredConcept] = Field(default_factory=list)
    common_mistakes: list[MistakePattern] = Field(default_factory=list)
    model_answer_html: str = Field(min_length=1)
    chapter_refs: list[str] = Field(default_factory=list)


class QuestionRubric(BaseModel):
    """Top-level rubric for one question baked into the simulator JSON."""

    model_config = ConfigDict(extra="forbid")
    question_id: str
    source_question_db_id: int
    type: QuestionType
    max_marks: int = Field(ge=0)
    stem: str
    figure_paths: list[str] = Field(default_factory=list)
    parts: list[RubricPart]


class SetPDFs(BaseModel):
    """Public URLs (relative to BASE_URL) of the printable artifacts for a set."""

    model_config = ConfigDict(extra="forbid")
    practice: str | None = None
    solutions: str | None = None


class SimulatorSet(BaseModel):
    """File baked into ``simulator/public/sets/<subject>-<chapter>.json``."""

    model_config = ConfigDict(extra="forbid")
    subject: str
    chapter: str
    generated_at: str
    questions: list[QuestionRubric]
    topic_index: dict[str, list[str]] = Field(
        default_factory=dict,
        description="topic -> list of question_ids; powers per-topic score breakdown",
    )
    pdfs: SetPDFs | None = None


# ---------------------------------------------------------------------------
# Step 0: Chapter priming (mandatory pre-step)
# ---------------------------------------------------------------------------


class ChapterPriming(BaseModel):
    """Audit log proving the agent has read every slide before any downstream work."""

    model_config = ConfigDict(extra="forbid")
    subject: str
    chapter_name: str
    slide_count_read: int = Field(ge=1)
    slide_paths: list[str] = Field(min_length=1)
    topics_covered: list[str] = Field(min_length=1)
    formulas_observed: list[str] = Field(default_factory=list)
    priming_notes: str
    confirms_no_slides_skipped: bool

    @field_validator("confirms_no_slides_skipped")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "confirms_no_slides_skipped must be True; re-prime by reading every slide"
            )
        return v


# ---------------------------------------------------------------------------
# Step 3.5: Extraction Auditor
# ---------------------------------------------------------------------------


class MissedQuestion(BaseModel):
    """A question the auditor sub-agent says the main agent skipped."""

    model_config = ConfigDict(extra="forbid")
    number: str
    type: QuestionType
    marks: int = Field(ge=0, le=50)
    stem: str
    sub_parts: list[SubPart] = Field(default_factory=list)
    options: list[MCQOption] | None = None
    figure_bboxes: list[BoundingBox] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class Misextraction(BaseModel):
    """An issue with an already-saved question that the auditor wants corrected."""

    model_config = ConfigDict(extra="forbid")
    question_db_id: int
    issue: str
    suggested_fix: str


class ExtractionAudit(BaseModel):
    """Independent auditor's verdict on a single extracted page."""

    model_config = ConfigDict(extra="forbid")
    paper_id: int
    page_idx: int = Field(ge=0)
    complete: bool
    missed_questions: list[MissedQuestion] = Field(default_factory=list)
    misextractions: list[Misextraction] = Field(default_factory=list)
    rationale: str
    audit_confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Step 5.5: Solution Judge + Improve loop
# ---------------------------------------------------------------------------


class JudgeDimensions(BaseModel):
    """Five dimensions, each scored 1..5 by the judge."""

    model_config = ConfigDict(extra="forbid")
    correctness: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    age_appropriateness: int = Field(ge=1, le=5)
    mark_scheme_alignment: int = Field(ge=1, le=5)
    completeness: int = Field(ge=1, le=5)


class JudgeIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "factual_error",
        "unclear_step",
        "vocabulary_too_advanced",
        "missing_step",
        "missing_chapter_reference",
        "off_topic",
        "formatting",
        "other",
    ]
    severity: Literal["low", "medium", "high"]
    description: str
    suggested_fix: str


class JudgeReport(BaseModel):
    """Pedagogical evaluation of a worked solution for a 15-year-old IGCSE student."""

    model_config = ConfigDict(extra="forbid")
    question_id: int
    chapter_id: int
    iteration: int = Field(ge=1)
    quality_score: float = Field(ge=0.0, le=1.0)
    dimensions: JudgeDimensions
    issues: list[JudgeIssue] = Field(default_factory=list)
    rewrite_required: bool
    improvement_brief: str
