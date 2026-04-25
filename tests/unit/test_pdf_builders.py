"""Smoke tests for the ReportLab PDF builders."""

from __future__ import annotations

from pathlib import Path

import fitz

from agent.generate.paper_pdf import PaperQuestion, build_practice_paper
from agent.generate.solutions_pdf import SolutionEntry, build_solutions_pdf


def test_build_practice_paper(tmp_path: Path):
    qs = [
        PaperQuestion(
            display_number=1,
            number="1",
            stem="Calculate the moles in 10g of calcium.",
            marks=3,
            sub_parts=[],
            options=None,
            figure_paths=[],
            source_label="Chem 2018 P2",
            fit="full",
        ),
        PaperQuestion(
            display_number=2,
            number="2",
            stem="Pick the correct answer.",
            marks=1,
            sub_parts=[],
            options=[
                {"label": "A", "text": "10 mol"},
                {"label": "B", "text": "0.25 mol"},
                {"label": "C", "text": "2.5 mol"},
            ],
            figure_paths=[],
            source_label="Chem 2019 P1",
            fit="partial",
        ),
    ]
    out = tmp_path / "paper.pdf"
    build_practice_paper("chemistry", "The Mole", qs, out)
    assert out.exists()
    doc = fitz.open(out)
    assert doc.page_count >= 2
    text_on_first = doc[0].get_text()
    assert "The Mole" in text_on_first or "mole" in text_on_first.lower()
    doc.close()


def test_build_solutions_pdf(tmp_path: Path):
    entries = [
        SolutionEntry(
            display_number=1,
            number="1",
            stem="Calculate moles.",
            figure_paths=[],
            source_label="Chem 2018 P2",
            out_of_scope=False,
            missing=[],
            final_answer="0.25 mol",
            steps=[{"number": 1, "explanation": "n = m/M = 10/40", "chapter_ref": "n=m/M"}],
            chapter_refs=["n=m/M"],
        ),
        SolutionEntry(
            display_number=2,
            number="2",
            stem="Stretch question.",
            figure_paths=[],
            source_label="Chem 2019 P4",
            out_of_scope=True,
            missing=["stoichiometry"],
            final_answer=None,
            steps=[],
            chapter_refs=[],
        ),
    ]
    out = tmp_path / "sol.pdf"
    build_solutions_pdf("chemistry", "The Mole", entries, out)
    assert out.exists()
    doc = fitz.open(out)
    text = "\n".join(page.get_text() for page in doc)
    assert "Review with teacher" in text or "Review" in text
    doc.close()
