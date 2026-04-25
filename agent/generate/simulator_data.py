"""Bake the per-chapter rubric JSON consumed by the static simulator.

Reads agent-produced ``QuestionRubric`` rows from SQLite, assembles them into
a ``SimulatorSet``, and writes ``simulator/public/sets/<subject>-<chapter>.json``.
Figure PNGs referenced by the rubric are copied to
``simulator/public/sets/figures/``. Practice + solutions PDFs (latest by
modification time) are copied to ``simulator/public/papers/<slug>/`` so they
are downloadable directly from the deployed GitHub Pages site.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from agent.config import output_dir, simulator_sets_dir
from agent.store.db import Chapter, Rubric, session_scope
from agent.store.schemas import QuestionRubric, SetPDFs, SimulatorSet


def _slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def _papers_public_dir() -> Path:
    return simulator_sets_dir().parent / "papers"


def _copy_latest_pdfs(subject: str, chapter_name: str) -> SetPDFs | None:
    """Copy the most recent practice + solutions PDFs into ``public/papers/<slug>/``.

    Returns relative URLs (without leading slash) suitable for the simulator
    fetch, or None when no PDFs exist yet for the chapter.
    """
    src = output_dir()
    if not src.exists():
        return None
    s_slug = _slug(subject)
    c_slug = _slug(chapter_name)
    slug = f"{s_slug}-{c_slug}"
    practice_glob = sorted(
        src.glob(f"practice_paper_{s_slug}_{c_slug}_*.pdf"),
        key=lambda p: p.stat().st_mtime,
    )
    solutions_glob = sorted(
        src.glob(f"solutions_{s_slug}_{c_slug}_*.pdf"),
        key=lambda p: p.stat().st_mtime,
    )
    if not practice_glob and not solutions_glob:
        return None
    dst = _papers_public_dir() / slug
    dst.mkdir(parents=True, exist_ok=True)
    pdfs = SetPDFs()
    if practice_glob:
        out = dst / "practice.pdf"
        shutil.copy2(practice_glob[-1], out)
        pdfs.practice = f"papers/{slug}/practice.pdf"
    if solutions_glob:
        out = dst / "solutions.pdf"
        shutil.copy2(solutions_glob[-1], out)
        pdfs.solutions = f"papers/{slug}/solutions.pdf"
    return pdfs


def bake_simulator_set(subject: str, chapter_name: str) -> Path:
    sets_dir = simulator_sets_dir()
    figures_dir = sets_dir / "figures"
    sets_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    with session_scope() as s:
        chapter = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter_name)
        ).scalar_one_or_none()
        if chapter is None:
            raise LookupError(f"Chapter not found: {subject}/{chapter_name}")

        rows = list(
            s.execute(select(Rubric).where(Rubric.chapter_id == chapter.id)).scalars()
        )
        if not rows:
            raise LookupError(
                f"No rubrics found for {subject}/{chapter_name}. "
                "Run `igcse build-simulator` after the agent has written rubrics."
            )

        rubrics: list[QuestionRubric] = []
        topic_index: dict[str, list[str]] = {}
        for row in rows:
            r = QuestionRubric.model_validate(row.rubric_json)
            copied_figs: list[str] = []
            for fig in r.figure_paths:
                src = Path(fig)
                if not src.exists():
                    continue
                dst = figures_dir / f"{_slug(r.question_id)}-{src.name}"
                if not dst.exists():
                    shutil.copy2(src, dst)
                copied_figs.append(f"./figures/{dst.name}")
            r.figure_paths = copied_figs
            rubrics.append(r)
            for part in r.parts:
                for cref in part.chapter_refs:
                    topic_index.setdefault(cref, []).append(r.question_id)

        pdfs = _copy_latest_pdfs(subject, chapter_name)

        baked = SimulatorSet(
            subject=subject,
            chapter=chapter_name,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            questions=rubrics,
            topic_index=topic_index,
            pdfs=pdfs,
        )

    out_path = sets_dir / f"{_slug(subject)}-{_slug(chapter_name)}.json"
    out_path.write_text(json.dumps(baked.model_dump(), indent=2), encoding="utf-8")

    _update_index(sets_dir)
    return out_path


def _update_index(sets_dir: Path) -> None:
    """Write ``sets/index.json`` listing all available sets for the simulator."""

    entries = []
    for p in sorted(sets_dir.glob("*.json")):
        if p.name == "index.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            pdfs = data.get("pdfs") or {}
            entries.append(
                {
                    "file": p.name,
                    "subject": data.get("subject"),
                    "chapter": data.get("chapter"),
                    "question_count": len(data.get("questions", [])),
                    "generated_at": data.get("generated_at"),
                    "pdfs": {
                        "practice": pdfs.get("practice"),
                        "solutions": pdfs.get("solutions"),
                    },
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    (sets_dir / "index.json").write_text(json.dumps({"sets": entries}, indent=2), encoding="utf-8")
