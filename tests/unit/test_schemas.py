"""Pydantic schema round-trip tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.store.schemas import (
    BoundingBox,
    ChapterProfile,
    ChapterTopic,
    CriticOutput,
    ExtractedQuestion,
    Fit,
    MatchDecision,
    MCQOption,
    PageExtraction,
    QuestionRubric,
    QuestionType,
    RubricPart,
    SolverOutput,
    SolverStep,
    SubPart,
)


def test_extracted_question_round_trip():
    q = ExtractedQuestion(
        number="1",
        type=QuestionType.STRUCTURED,
        marks=4,
        stem="Calculate the number of moles.",
        sub_parts=[SubPart(label="a", prompt="state formula", marks=1)],
        figure_bboxes=[BoundingBox(x=0.1, y=0.2, w=0.3, h=0.4)],
        confidence=0.92,
    )
    dumped = q.model_dump()
    restored = ExtractedQuestion.model_validate(dumped)
    assert restored == q


def test_page_extraction_empty_ok():
    pe = PageExtraction(paper_id=1, page_idx=0, questions=[])
    assert pe.questions == []


def test_mcq_requires_two_options():
    with pytest.raises(ValidationError):
        ExtractedQuestion(
            number="1",
            type=QuestionType.MCQ,
            marks=1,
            stem="Which?",
            options=[MCQOption(label="A", text="only one")],
            confidence=0.9,
        )


def test_chapter_profile_minimum():
    cp = ChapterProfile(
        subject="chemistry",
        chapter_name="The Mole",
        syllabus_topics=[
            ChapterTopic(name="Moles", summary="n=m/M", key_terms=["mole", "molar"])
        ],
    )
    assert cp.subject == "chemistry"
    assert cp.syllabus_topics[0].name == "Moles"


def test_match_decision_fit_enum():
    md = MatchDecision(
        chapter_id=1, question_id=7, fit=Fit.PARTIAL, score=0.81, rationale="uses mole"
    )
    assert md.fit is Fit.PARTIAL
    assert 0 <= md.score <= 1


def test_solver_round_trip():
    so = SolverOutput(
        question_id=1,
        chapter_id=1,
        out_of_scope=False,
        final_answer="0.25 mol",
        steps=[SolverStep(number=1, explanation="n = m/M", chapter_ref="n=m/M")],
        chapter_refs=["n=m/M"],
    )
    restored = SolverOutput.model_validate(so.model_dump())
    assert restored.steps[0].number == 1


def test_critic_issues_default():
    co = CriticOutput(question_id=1, chapter_id=1, agrees=True, final_answer="0.25 mol")
    assert co.issues == []
    assert co.chapter_alignment_ok is True


def test_rubric_numeric_part():
    part = RubricPart(
        id="a",
        prompt="Calculate n.",
        answer_type="numeric",
        max_marks=3,
        numeric_answer=0.25,
        numeric_unit="mol",
        numeric_tolerance_pct=2.0,
        model_answer_html="<p>0.25 mol</p>",
        chapter_refs=["n = m/M"],
    )
    qr = QuestionRubric(
        question_id="q1",
        source_question_db_id=1,
        type=QuestionType.NUMERIC,
        max_marks=3,
        stem="Calculate n.",
        parts=[part],
    )
    data = qr.model_dump_json()
    restored = QuestionRubric.model_validate_json(data)
    assert restored.parts[0].numeric_answer == 0.25


def test_bbox_out_of_range_rejected():
    with pytest.raises(ValidationError):
        BoundingBox(x=0.1, y=0.2, w=1.2, h=0.3)


def test_question_unknown_field_rejected():
    with pytest.raises(ValidationError):
        ExtractedQuestion.model_validate(
            {
                "number": "1",
                "type": "short",
                "marks": 1,
                "stem": "x",
                "confidence": 0.9,
                "bogus": True,
            }
        )
