"""Matcher shortlist + dedup tests using fake embeddings."""

from __future__ import annotations

import pytest

from agent.match import dedup_questions, shortlist_candidates
from agent.store.db import Chapter, Page, Paper, Question, session_scope


def _seed(questions: list[tuple[str, str, str]]) -> dict[str, int]:
    """questions: list of (subject, number, stem). Returns name->id."""

    with session_scope() as s:
        s.add(
            Chapter(
                subject="chemistry",
                name="Moles",
                profile_json={
                    "subject": "chemistry",
                    "chapter_name": "Moles",
                    "syllabus_topics": [
                        {"name": "Moles", "summary": "n = m / M", "key_terms": ["mole", "n=m/M"]}
                    ],
                    "definitions": [],
                    "formulas": ["n = m / M"],
                    "worked_examples": [],
                    "vocabulary": ["mole"],
                    "out_of_scope_notes": [],
                },
                screenshot_paths_json=[],
            )
        )
        ids: dict[str, int] = {}
        for i, (subject, number, stem) in enumerate(questions):
            paper = Paper(
                subject=subject,
                path=f"/tmp/{subject}-{number}-{i}.pdf",
                hash=f"{subject}-{number}-{i}",
            )
            s.add(paper)
            s.flush()
            page = Page(paper_id=paper.id, idx=0, png_path="/tmp/p.png")
            s.add(page)
            s.flush()
            q = Question(
                paper_id=paper.id,
                page_id=page.id,
                number=number,
                type="short",
                marks=1,
                stem=stem,
                sub_parts_json=[],
            )
            s.add(q)
            s.flush()
            ids[number] = q.id
        return ids


def test_shortlist_returns_same_subject_only(fake_embed_env):
    _seed(
        [
            ("chemistry", "1", "Calculate moles of calcium."),
            ("physics", "1", "Calculate current in a circuit."),
        ]
    )
    out = shortlist_candidates(
        subject="chemistry", chapter_name="Moles", top_k=10, similarity_floor=-1.0
    )
    assert len(out) == 1
    assert out[0].number == "1"


def test_shortlist_missing_chapter_raises(fake_embed_env):
    with pytest.raises(LookupError):
        shortlist_candidates(subject="chemistry", chapter_name="Nope")


def test_dedup_drops_identical_stems(fake_embed_env):
    ids = _seed(
        [
            ("chemistry", "1", "Calculate moles of calcium."),
            ("chemistry", "2", "Calculate moles of calcium."),
            ("chemistry", "3", "Explain electrolysis."),
        ]
    )
    kept = dedup_questions(list(ids.values()), cosine_threshold=0.99)
    assert len(kept) == 2


def test_dedup_high_threshold_keeps_all(fake_embed_env):
    ids = _seed(
        [
            ("chemistry", "1", "Q1"),
            ("chemistry", "2", "Q2"),
        ]
    )
    kept = dedup_questions(list(ids.values()), cosine_threshold=0.999999)
    assert len(kept) == 2
