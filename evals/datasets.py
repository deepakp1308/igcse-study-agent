"""Typed loaders for the eval YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

HERE = Path(__file__).parent


class ChapterMatchCase(BaseModel):
    id: str
    subject: str
    chapter: str
    question_stem: str
    should_match: bool
    notes: str | None = None


class SolutionQualityCase(BaseModel):
    id: str
    subject: str
    chapter: str
    question_stem: str
    gold_final_answer: str
    gold_chapter_refs: list[str] = Field(default_factory=list)
    gold_steps: list[str] = Field(default_factory=list)


class RubricGraderCase(BaseModel):
    id: str
    rubric: dict[str, Any]
    student_answers: dict[str, Any]
    gold_marks: float
    tolerance: float = 0.5


def load_chapter_match() -> list[ChapterMatchCase]:
    data = yaml.safe_load((HERE / "chapter_match.yaml").read_text())
    return [ChapterMatchCase.model_validate(row) for row in data.get("cases", [])]


def load_solution_quality() -> list[SolutionQualityCase]:
    data = yaml.safe_load((HERE / "solution_quality.yaml").read_text())
    return [SolutionQualityCase.model_validate(row) for row in data.get("cases", [])]


def load_rubric_grader() -> list[RubricGraderCase]:
    data = yaml.safe_load((HERE / "rubric_grader.yaml").read_text())
    return [RubricGraderCase.model_validate(row) for row in data.get("cases", [])]
