"""End-to-end smoke: ingest -> chapter -> match -> paper -> solutions -> rubric -> set bake.

Uses fake embeddings, synthesized PDFs, and canned agent JSON fixtures so this
runs fully offline. Exercises the deterministic surfaces the Cursor agent
relies on in production.
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from agent.cli import app
from agent.generate.simulator_data import bake_simulator_set
from agent.ingest.render import ingest_papers_folder
from agent.store.db import Chapter, Question, session_scope


def _make_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    for line in lines:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), line, fontsize=14)
    doc.save(str(path))
    doc.close()


@pytest.mark.e2e
def test_full_pipeline(tmp_path: Path):
    runner = CliRunner()

    # 1. Synthesize a papers corpus: one chemistry paper with two pages.
    papers_root = tmp_path / "papers" / "chemistry"
    papers_root.mkdir(parents=True)
    _make_pdf(
        papers_root / "0620_22_2018.pdf",
        [
            "Q1. Calculate the number of moles in 10 g of calcium. [3]",
            "Q2. State what is meant by electrolysis. [1]",
        ],
    )
    results = ingest_papers_folder(tmp_path / "papers")
    assert len(results) == 1
    pid = results[0].paper_id

    # 2. Save paper metadata.
    r = runner.invoke(
        app,
        ["save-paper-metadata", "--paper-id", str(pid), "-"],
        input=json.dumps(
            {
                "subject": "chemistry",
                "year": 2018,
                "paper_number": "2",
                "tier": "extended",
                "confidence": 0.95,
            }
        ),
    )
    assert r.exit_code == 0

    # 3. Save agent-extracted questions for two pages.
    for page_idx, q in enumerate(
        [
            {
                "number": "1",
                "type": "numeric",
                "marks": 3,
                "stem": "Calculate the number of moles in 10 g of calcium. Ar(Ca) = 40.",
                "confidence": 0.93,
            },
            {
                "number": "2",
                "type": "short",
                "marks": 1,
                "stem": "State what is meant by electrolysis.",
                "confidence": 0.9,
            },
        ]
    ):
        r = runner.invoke(
            app,
            [
                "save-questions",
                "--paper-id",
                str(pid),
                "--page-idx",
                str(page_idx),
                "-",
            ],
            input=json.dumps({"paper_id": pid, "page_idx": page_idx, "questions": [q]}),
        )
        assert r.exit_code == 0, r.stdout

    # 4. Save a chapter profile covering question 1 (The Mole).
    r = runner.invoke(
        app,
        ["save-chapter", "--subject", "chemistry", "--name", "The Mole", "-"],
        input=json.dumps(
            {
                "subject": "chemistry",
                "chapter_name": "The Mole",
                "syllabus_topics": [
                    {
                        "name": "Moles",
                        "summary": "n = m / M is used to calculate moles.",
                        "key_terms": ["mole", "molar mass"],
                    }
                ],
                "definitions": ["mole: SI unit amount of substance"],
                "formulas": ["n = m / M"],
                "worked_examples": [],
                "vocabulary": ["mole"],
                "out_of_scope_notes": [],
            }
        ),
    )
    assert r.exit_code == 0

    with session_scope() as s:
        chapter_id = s.execute(
            select(Chapter.id).where(
                Chapter.subject == "chemistry", Chapter.name == "The Mole"
            )
        ).scalar_one()
        q1_id = s.execute(
            select(Question.id).where(Question.number == "1")
        ).scalar_one()
        q2_id = s.execute(
            select(Question.id).where(Question.number == "2")
        ).scalar_one()

    # 5. Save match decisions (agent judgment).
    for qid, fit, score, rationale in [
        (q1_id, "full", 0.95, "Uses n = m/M straight from chapter"),
        (q2_id, "none", 0.1, "Electrolysis is a different chapter"),
    ]:
        r = runner.invoke(
            app,
            ["save-match", "-"],
            input=json.dumps(
                {
                    "chapter_id": chapter_id,
                    "question_id": qid,
                    "fit": fit,
                    "score": score,
                    "rationale": rationale,
                    "missing_concepts": [],
                }
            ),
        )
        assert r.exit_code == 0, r.stdout

    # 6. Generate practice paper PDF.
    r = runner.invoke(
        app,
        [
            "generate-paper",
            "--subject",
            "chemistry",
            "--chapter",
            "The Mole",
        ],
    )
    assert r.exit_code == 0, r.stdout
    pdfs = list((tmp_path / "output").glob("practice_paper_*.pdf"))
    assert len(pdfs) == 1

    # 7. Save solver + critic for q1, then build solutions PDF.
    r = runner.invoke(
        app,
        ["save-solution", "-"],
        input=json.dumps(
            {
                "question_id": q1_id,
                "chapter_id": chapter_id,
                "out_of_scope": False,
                "final_answer": "0.25 mol",
                "steps": [
                    {
                        "number": 1,
                        "explanation": "n = m/M = 10/40",
                        "chapter_ref": "n = m / M",
                    }
                ],
                "chapter_refs": ["n = m / M"],
            }
        ),
    )
    assert r.exit_code == 0, r.stdout
    r = runner.invoke(
        app,
        ["save-critic", "-"],
        input=json.dumps(
            {
                "question_id": q1_id,
                "chapter_id": chapter_id,
                "agrees": True,
                "final_answer": "0.25 mol",
            }
        ),
    )
    assert r.exit_code == 0, r.stdout

    r = runner.invoke(
        app,
        [
            "generate-solutions",
            "--subject",
            "chemistry",
            "--chapter",
            "The Mole",
        ],
    )
    assert r.exit_code == 0, r.stdout
    sols = list((tmp_path / "output").glob("solutions_*.pdf"))
    assert len(sols) == 1

    # 8. Save a rubric and bake simulator set.
    r = runner.invoke(
        app,
        ["save-rubric", "--chapter-id", str(chapter_id), "-"],
        input=json.dumps(
            {
                "question_id": "2018-chem-p2-q1",
                "source_question_db_id": q1_id,
                "type": "numeric",
                "max_marks": 3,
                "stem": "Calculate the number of moles in 10 g of calcium.",
                "figure_paths": [],
                "parts": [
                    {
                        "id": "a",
                        "prompt": "Calculate n.",
                        "answer_type": "numeric",
                        "max_marks": 3,
                        "numeric_answer": 0.25,
                        "numeric_unit": "mol",
                        "numeric_tolerance_pct": 2.0,
                        "accepted_phrasings": [],
                        "required_working_concepts": [
                            {
                                "concept": "uses n = m/M",
                                "marks": 1,
                                "hints": ["n = m/M"],
                            }
                        ],
                        "common_mistakes": [],
                        "model_answer_html": "<p>0.25 mol</p>",
                        "chapter_refs": ["n = m / M"],
                    }
                ],
            }
        ),
    )
    assert r.exit_code == 0, r.stdout

    baked = bake_simulator_set("chemistry", "The Mole")
    assert baked.exists()
    data = json.loads(baked.read_text())
    assert data["subject"] == "chemistry"
    assert data["chapter"] == "The Mole"
    assert len(data["questions"]) == 1

    index_file = baked.parent / "index.json"
    assert index_file.exists()
    index = json.loads(index_file.read_text())
    assert any(entry["file"] == baked.name for entry in index["sets"])

    # 9. Dashboard writes markdown summary.
    dash_path = tmp_path / "QUALITY_DASHBOARD.md"
    r = runner.invoke(app, ["dashboard", "--output", str(dash_path)])
    assert r.exit_code == 0, r.stdout
    assert dash_path.exists()
    content = dash_path.read_text()
    assert "Papers ingested" in content
    assert "Rubrics generated" in content
