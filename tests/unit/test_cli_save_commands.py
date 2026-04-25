"""Tests for the save-* CLI commands that validate agent JSON into SQLite."""

from __future__ import annotations

import json
from pathlib import Path

import fitz
from sqlalchemy import select
from typer.testing import CliRunner

from agent.cli import app
from agent.ingest.render import ingest_papers_folder
from agent.store.db import Chapter, Match, Paper, Question, Rubric, Solution, session_scope


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((72, 120), "Q1 What is 2+2?", fontsize=14)
    doc.save(str(path))
    doc.close()


def _seed_paper(tmp_path: Path) -> int:
    root = tmp_path / "papers" / "chemistry"
    root.mkdir(parents=True)
    _make_pdf(root / "paper.pdf")
    results = ingest_papers_folder(tmp_path / "papers")
    return results[0].paper_id


def test_save_paper_metadata(tmp_path: Path):
    pid = _seed_paper(tmp_path)
    payload = {
        "subject": "chemistry",
        "year": 2018,
        "paper_number": "2",
        "tier": "extended",
        "total_marks": 80,
        "confidence": 0.9,
    }
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["save-paper-metadata", "--paper-id", str(pid), "-"],
        input=json.dumps(payload),
    )
    assert result.exit_code == 0, result.stdout
    with session_scope() as s:
        paper = s.get(Paper, pid)
        assert paper is not None
        assert paper.year == 2018
        assert paper.tier == "extended"


def test_save_questions_creates_rows_and_crops(tmp_path: Path):
    pid = _seed_paper(tmp_path)
    payload = {
        "paper_id": pid,
        "page_idx": 0,
        "questions": [
            {
                "number": "1",
                "type": "short",
                "marks": 2,
                "stem": "What is 2+2?",
                "confidence": 0.95,
                "figure_bboxes": [{"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3}],
            }
        ],
    }
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["save-questions", "--paper-id", str(pid), "--page-idx", "0", "-"],
        input=json.dumps(payload),
    )
    assert result.exit_code == 0, result.stdout
    with session_scope() as s:
        rows = list(s.execute(select(Question).where(Question.paper_id == pid)).scalars())
        assert len(rows) == 1
        assert rows[0].figure_paths_json
        assert Path(rows[0].figure_paths_json[0]).exists()


def test_save_questions_rejects_bad_schema(tmp_path: Path):
    pid = _seed_paper(tmp_path)
    runner = CliRunner()
    # missing required `stem`
    bad = {
        "paper_id": pid,
        "page_idx": 0,
        "questions": [{"number": "1", "type": "short", "marks": 1, "confidence": 0.9}],
    }
    result = runner.invoke(
        app,
        ["save-questions", "--paper-id", str(pid), "--page-idx", "0", "-"],
        input=json.dumps(bad),
    )
    assert result.exit_code == 2


def test_save_chapter_and_match_and_rubric_flow(tmp_path: Path):
    pid = _seed_paper(tmp_path)
    runner = CliRunner()

    # seed one question
    qpayload = {
        "paper_id": pid,
        "page_idx": 0,
        "questions": [
            {
                "number": "1",
                "type": "numeric",
                "marks": 3,
                "stem": "Calculate moles.",
                "confidence": 0.9,
            }
        ],
    }
    runner.invoke(
        app,
        ["save-questions", "--paper-id", str(pid), "--page-idx", "0", "-"],
        input=json.dumps(qpayload),
    )
    with session_scope() as s:
        qid = s.execute(select(Question.id).where(Question.paper_id == pid)).scalar_one()

    # chapter
    cp = {
        "subject": "chemistry",
        "chapter_name": "The Mole",
        "syllabus_topics": [{"name": "Moles", "summary": "n=m/M", "key_terms": ["mole"]}],
        "definitions": [],
        "formulas": ["n = m/M"],
        "worked_examples": [],
        "vocabulary": ["mole"],
        "out_of_scope_notes": [],
    }
    r = runner.invoke(
        app,
        ["save-chapter", "--subject", "chemistry", "--name", "The Mole", "-"],
        input=json.dumps(cp),
    )
    assert r.exit_code == 0, r.stdout
    with session_scope() as s:
        chapter_id = s.execute(
            select(Chapter.id).where(Chapter.subject == "chemistry", Chapter.name == "The Mole")
        ).scalar_one()

    # match
    md = {
        "chapter_id": chapter_id,
        "question_id": qid,
        "fit": "full",
        "score": 0.9,
        "rationale": "uses mole formula",
        "missing_concepts": [],
    }
    r = runner.invoke(app, ["save-match", "-"], input=json.dumps(md))
    assert r.exit_code == 0, r.stdout
    with session_scope() as s:
        m = s.get(Match, (chapter_id, qid))
        assert m is not None and m.fit == "full"

    # solver + critic
    so = {
        "question_id": qid,
        "chapter_id": chapter_id,
        "out_of_scope": False,
        "final_answer": "0.25 mol",
        "steps": [{"number": 1, "explanation": "n = m/M = 10/40", "chapter_ref": "n=m/M"}],
        "chapter_refs": ["n=m/M"],
    }
    r = runner.invoke(app, ["save-solution", "-"], input=json.dumps(so))
    assert r.exit_code == 0, r.stdout
    co = {
        "question_id": qid,
        "chapter_id": chapter_id,
        "agrees": True,
        "final_answer": "0.25 mol",
    }
    r = runner.invoke(app, ["save-critic", "-"], input=json.dumps(co))
    assert r.exit_code == 0, r.stdout
    with session_scope() as s:
        sol = s.get(Solution, (qid, chapter_id))
        assert sol is not None and sol.critic_agrees is True and sol.reconciled_json is not None

    # rubric
    rub = {
        "question_id": "2018-chem-p2-q1",
        "source_question_db_id": qid,
        "type": "numeric",
        "max_marks": 3,
        "stem": "Calculate moles.",
        "figure_paths": [],
        "parts": [
            {
                "id": "a",
                "prompt": "Calculate moles.",
                "answer_type": "numeric",
                "max_marks": 3,
                "numeric_answer": 0.25,
                "numeric_unit": "mol",
                "numeric_tolerance_pct": 2.0,
                "accepted_phrasings": [],
                "required_working_concepts": [
                    {"concept": "uses n=m/M", "marks": 1, "hints": ["n = m/M"]}
                ],
                "common_mistakes": [],
                "model_answer_html": "<p>0.25 mol</p>",
                "chapter_refs": ["n = m/M"],
            }
        ],
    }
    r = runner.invoke(
        app, ["save-rubric", "--chapter-id", str(chapter_id), "-"], input=json.dumps(rub)
    )
    assert r.exit_code == 0, r.stdout
    with session_scope() as s:
        row = s.get(Rubric, (qid, chapter_id))
        assert row is not None
