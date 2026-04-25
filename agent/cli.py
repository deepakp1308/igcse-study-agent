"""Typer CLI.

All LLM work (extraction, chapter profiling, matching, solving, rubric
building) is done by the Cursor agent. These commands are the deterministic
scaffolding around that work:

* ``ingest-papers`` and ``ingest-chapters`` render inputs and print
  per-page / per-chapter **agent instructions** the Cursor agent follows
  turn-by-turn.
* ``save-questions``, ``save-chapter``, ``save-match``, ``save-solution``,
  ``save-rubric`` accept JSON (file or stdin) matching a pydantic schema and
  write validated rows to SQLite. On validation failure they park the raw
  response in ``review_queue``.
* ``match``, ``generate-paper``, ``generate-solutions``, ``build-simulator``,
  ``deploy`` do deterministic layout / shortlisting / git work.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable
from sqlalchemy import select

from agent import __version__
from agent.config import (
    CRITIC_DISAGREEMENT_BLOCK_RATE,
    DEDUP_COSINE_DEFAULT,
    LOW_CONFIDENCE_THRESHOLD,
    MATCH_THRESHOLD_DEFAULT,
    figures_cache_dir,
    output_dir,
    pages_cache_dir,
    simulator_dist_dir,
    simulator_sets_dir,
)
from agent.generate.paper_pdf import PaperQuestion, build_practice_paper
from agent.generate.simulator_data import bake_simulator_set
from agent.generate.solutions_pdf import SolutionEntry, build_solutions_pdf
from agent.ingest.crops import crop_bboxes_to_files
from agent.ingest.render import ingest_papers_folder
from agent.match import dedup_questions, shortlist_candidates
from agent.review.queue import add_review, list_pending, resolve
from agent.store.db import (
    Chapter,
    ExtractionAuditRow,
    Match,
    Page,
    Paper,
    Question,
    Rubric,
    Solution,
    init_db,
    session_scope,
)
from agent.store.schemas import (
    BoundingBox,
    ChapterPriming,
    ChapterProfile,
    CriticOutput,
    ExtractionAudit,
    JudgeReport,
    MatchDecision,
    PageExtraction,
    PaperMetadata,
    QuestionRubric,
    SolverOutput,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("igcse")

app = typer.Typer(
    help="IGCSE past-paper study agent. Zero-API-key pipeline: the Cursor agent "
    "does the LLM work; this CLI does the deterministic work.",
    no_args_is_help=True,
)
console = Console()


def _version_cb(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_cb, is_eager=True, help="Show version and exit"),
    ] = False,
) -> None:
    pass


def _read_json_payload(payload: str | None) -> dict[str, object] | list[dict[str, object]]:
    if payload in (None, "-"):
        data = sys.stdin.read()
    else:
        p = Path(payload)  # type: ignore[arg-type]
        data = p.read_text(encoding="utf-8") if p.exists() else payload  # type: ignore[assignment]
    try:
        parsed: dict[str, object] | list[dict[str, object]] = json.loads(data)
        return parsed
    except json.JSONDecodeError as e:
        raise typer.BadParameter(f"Invalid JSON: {e}") from e


def _slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in s).strip("-")


def _list_chapter_slides(subject: str, chapter: str) -> list[Path]:
    """Return slide paths for a chapter folder.

    Looks up by stored screenshot_paths first; falls back to scanning
    ``chapters/<subject>/<chapter>/`` under the repo root.
    """
    init_db()
    with session_scope() as s:
        chapter_row = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter)
        ).scalar_one_or_none()
        stored: list[str] = (
            list(chapter_row.screenshot_paths_json or [])
            if chapter_row is not None
            else []
        )
    if stored:
        return [Path(p) for p in stored if Path(p).exists()]
    fallback = (
        Path(__file__).resolve().parent.parent
        / "chapters"
        / subject.replace(" ", "_")
        / chapter
    )
    if fallback.is_dir():
        return sorted(
            [
                *fallback.glob("*.png"),
                *fallback.glob("*.jpg"),
                *fallback.glob("*.jpeg"),
            ]
        )
    return []


def _ensure_primed(subject: str, chapter: str) -> None:
    """Hard precondition for downstream steps."""
    init_db()
    with session_scope() as s:
        row = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter)
        ).scalar_one_or_none()
        if row is None:
            raise typer.BadParameter(
                f"Chapter not found: {subject}/{chapter}. "
                "Run `igcse save-chapter` first."
            )
        if row.primed_at is None:
            console.print(
                Panel.fit(
                    f"Chapter {subject}/{chapter} has NOT been primed.\n"
                    f"Run `igcse chapter-prime --subject \"{subject}\" --chapter \"{chapter}\"` "
                    "and complete the priming turn first.",
                    title="[red]PRIMING REQUIRED[/]",
                    border_style="red",
                )
            )
            raise typer.Exit(code=4)


def _print_agent_instructions(title: str, body: str) -> None:
    console.print(
        Panel.fit(
            body,
            title=f"[bold yellow]AGENT INSTRUCTIONS: {title}[/]",
            border_style="yellow",
        )
    )


# ---------------------------------------------------------------------------
# ingest-papers / save-questions / save-paper-metadata
# ---------------------------------------------------------------------------


@app.command("ingest-papers")
def cmd_ingest_papers(
    papers_dir: Annotated[
        Path,
        typer.Option("--papers-dir", exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    ],
    show_instructions: Annotated[bool, typer.Option("--instructions/--no-instructions")] = True,
) -> None:
    """Render every PDF under PAPERS_DIR to page PNGs, upsert rows in SQLite."""

    init_db()
    results = ingest_papers_folder(papers_dir)
    t = RichTable(title="Ingested papers")
    t.add_column("paper_id")
    t.add_column("path")
    t.add_column("pages")
    t.add_column("status")
    for r in results:
        t.add_row(
            str(r.paper_id),
            str(r.path.relative_to(papers_dir) if r.path.is_relative_to(papers_dir) else r.path),
            str(r.page_count),
            "cached" if r.reused else "new",
        )
    console.print(t)

    if show_instructions:
        _print_agent_instructions(
            "extract questions per page",
            "For each paper listed above, run one turn per page:\n"
            "  1. Read the PNG at `pages_cache/paper-<id>/page-<NNNN>.png` (absolute path logged).\n"
            "  2. Extract questions using `prompts/extract_questions.md`.\n"
            "  3. Return a JSON payload matching schema `PageExtraction`.\n"
            "  4. Save via: `igcse save-questions --paper-id <id> --page-idx <N> -`\n"
            "     (pipe the JSON via stdin).\n"
            "Also, for each new paper, run once at the start:\n"
            "  `igcse save-paper-metadata --paper-id <id> -` with JSON matching `PaperMetadata`.",
        )


@app.command("save-paper-metadata")
def cmd_save_paper_metadata(
    paper_id: Annotated[int, typer.Option("--paper-id")],
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist the agent's PaperMetadata extraction (subject, year, tier, ...)."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        meta = PaperMetadata.model_validate(raw)
    except ValidationError as e:
        add_review("paper_metadata", f"paper_id={paper_id}", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e
    with session_scope() as s:
        paper = s.get(Paper, paper_id)
        if paper is None:
            raise typer.BadParameter(f"No paper with id {paper_id}")
        paper.subject = meta.subject
        paper.year = meta.year
        paper.session = meta.session
        paper.paper_number = meta.paper_number
        paper.tier = meta.tier
        paper.total_marks = meta.total_marks
        paper.metadata_confidence = meta.confidence
    console.print(f"[green]Updated metadata for paper {paper_id}[/]")


@app.command("save-questions")
def cmd_save_questions(
    paper_id: Annotated[int, typer.Option("--paper-id")],
    page_idx: Annotated[int, typer.Option("--page-idx")],
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist extracted questions for one page; crops figure bboxes to PNGs."""

    init_db()
    raw = _read_json_payload(payload)
    if isinstance(raw, list):
        raw = {"paper_id": paper_id, "page_idx": page_idx, "questions": raw}
    if isinstance(raw, dict):
        raw.setdefault("paper_id", paper_id)
        raw.setdefault("page_idx", page_idx)
    try:
        page_ext = PageExtraction.model_validate(raw)
    except ValidationError as e:
        add_review(
            "page_extraction",
            f"paper_id={paper_id} page_idx={page_idx}",
            f"schema: {e}",
            json.dumps(raw),
        )
        console.print("[red]schema validation failed, routed to review_queue[/]")
        raise typer.Exit(code=2) from e

    low_conf = 0
    with session_scope() as s:
        page = s.execute(
            select(Page).where(Page.paper_id == paper_id, Page.idx == page_idx)
        ).scalar_one_or_none()
        if page is None:
            raise typer.BadParameter(f"No page idx={page_idx} for paper_id={paper_id}")

        for q in page_ext.questions:
            row = Question(
                paper_id=paper_id,
                page_id=page.id,
                number=q.number,
                type=q.type.value,
                marks=q.marks,
                stem=q.stem,
                sub_parts_json=[sp.model_dump() for sp in q.sub_parts],
                options_json=[o.model_dump() for o in q.options] if q.options else None,
                figure_paths_json=[],
                figure_bboxes_json=[bb.model_dump() for bb in q.figure_bboxes],
                confidence=q.confidence,
                notes=q.notes,
            )
            s.add(row)
            if q.confidence < LOW_CONFIDENCE_THRESHOLD:
                low_conf += 1
                add_review(
                    "low_confidence_question",
                    f"paper_id={paper_id} page_idx={page_idx} q={q.number}",
                    f"confidence={q.confidence:.2f}",
                    json.dumps(q.model_dump()),
                )

    msg = (
        f"[green]Saved {len(page_ext.questions)} questions for paper {paper_id} "
        f"page {page_idx} (figure crops deferred until audit pass)[/]"
    )
    if low_conf:
        msg += f" [yellow]({low_conf} flagged for review)[/]"
    console.print(msg)


# ---------------------------------------------------------------------------
# ingest-chapters / save-chapter
# ---------------------------------------------------------------------------


@app.command("ingest-chapters")
def cmd_ingest_chapters(
    chapters_dir: Annotated[
        Path,
        typer.Option(
            "--chapters-dir",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ],
) -> None:
    """Enumerate ``Subject/Chapter/*.png`` and print agent instructions."""

    init_db()
    candidates = []
    for subject_dir in sorted(p for p in chapters_dir.iterdir() if p.is_dir()):
        for chapter_dir in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
            images = sorted(
                [*chapter_dir.glob("*.png"), *chapter_dir.glob("*.jpg"), *chapter_dir.glob("*.jpeg")]
            )
            if not images:
                continue
            candidates.append((subject_dir.name, chapter_dir.name, images))

    t = RichTable(title="Chapters discovered")
    t.add_column("subject")
    t.add_column("chapter")
    t.add_column("screenshots")
    for subject, chapter, imgs in candidates:
        t.add_row(subject, chapter, str(len(imgs)))
    console.print(t)

    if not candidates:
        console.print("[yellow]No chapter folders found. Expected Subject/Chapter/*.png[/]")
        return

    body_lines = [
        "For each chapter listed above:",
        "  1. Open each screenshot in order using the Read tool.",
        "  2. Use prompt `prompts/chapter_profile.md`.",
        "  3. Return JSON matching schema `ChapterProfile`.",
        "  4. Save via: `igcse save-chapter --subject <S> --name <C> -`",
        "     (pipe the JSON via stdin; screenshot paths are auto-captured).",
        "",
        "Chapter screenshot file paths to read, per chapter:",
    ]
    for subject, chapter, imgs in candidates:
        body_lines.append(f"  - {subject}/{chapter}:")
        for img in imgs:
            body_lines.append(f"      {img}")
    _print_agent_instructions("build chapter profiles", "\n".join(body_lines))


@app.command("save-chapter")
def cmd_save_chapter(
    subject: Annotated[str, typer.Option("--subject")],
    name: Annotated[str, typer.Option("--name")],
    screenshots_dir: Annotated[
        Path | None,
        typer.Option("--screenshots-dir", exists=True, file_okay=False, dir_okay=True),
    ] = None,
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist a ChapterProfile for subject/name."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        profile = ChapterProfile.model_validate(raw)
    except ValidationError as e:
        add_review("chapter_profile", f"{subject}/{name}", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e

    screenshots: list[str] = []
    if screenshots_dir:
        screenshots = [
            str(p)
            for p in sorted(
                [
                    *screenshots_dir.glob("*.png"),
                    *screenshots_dir.glob("*.jpg"),
                    *screenshots_dir.glob("*.jpeg"),
                ]
            )
        ]

    with session_scope() as s:
        existing = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == name)
        ).scalar_one_or_none()
        if existing is None:
            s.add(
                Chapter(
                    subject=subject,
                    name=name,
                    profile_json=profile.model_dump(),
                    screenshot_paths_json=screenshots,
                )
            )
        else:
            existing.profile_json = profile.model_dump()
            if screenshots:
                existing.screenshot_paths_json = screenshots
    console.print(f"[green]Saved chapter profile: {subject}/{name}[/]")


# ---------------------------------------------------------------------------
# match / save-match
# ---------------------------------------------------------------------------


@app.command("match")
def cmd_match(
    subject: Annotated[str, typer.Option("--subject")],
    chapter: Annotated[str, typer.Option("--chapter")],
    top_k: Annotated[int, typer.Option("--top-k")] = 60,
    similarity_floor: Annotated[float, typer.Option("--sim-floor")] = 0.25,
) -> None:
    """Produce a ranked candidate shortlist and print agent instructions."""

    init_db()
    _ensure_primed(subject, chapter)
    candidates = shortlist_candidates(
        subject=subject, chapter_name=chapter, top_k=top_k, similarity_floor=similarity_floor
    )
    t = RichTable(title=f"Candidates for {subject} / {chapter}")
    t.add_column("question_id")
    t.add_column("paper_id")
    t.add_column("number")
    t.add_column("type")
    t.add_column("marks")
    t.add_column("sim")
    for c in candidates:
        t.add_row(
            str(c.question_id),
            str(c.paper_id),
            c.number,
            c.type,
            str(c.marks),
            f"{c.similarity:.2f}",
        )
    console.print(t)

    if not candidates:
        console.print("[yellow]No candidates above similarity floor.[/]")
        return

    with session_scope() as s:
        chapter_row = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter)
        ).scalar_one()
        chapter_id = chapter_row.id
        profile = json.dumps(chapter_row.profile_json, indent=2)

    body_lines = [
        f"Chapter id = {chapter_id}. For each candidate question id above:",
        "  1. Read the question stem (above) + the candidate's page PNG if needed.",
        "  2. Use prompt `prompts/match_verify.md` with the chapter profile below.",
        "  3. Return JSON matching `MatchDecision`.",
        "  4. Save via: `igcse save-match -` (pipe JSON via stdin).",
        "",
        "Decide precision-first: only classify `fit=full` when the chapter fully ",
        "covers everything the question tests. `partial` if mostly but needs a little ",
        "outside-chapter content. `none` otherwise.",
        "",
        "Chapter profile JSON:",
        profile,
    ]
    _print_agent_instructions("verify chapter matches", "\n".join(body_lines))


@app.command("save-match")
def cmd_save_match(
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist one MatchDecision row."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        decision = MatchDecision.model_validate(raw)
    except ValidationError as e:
        add_review("match_decision", "", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e
    with session_scope() as s:
        row = s.get(Match, (decision.chapter_id, decision.question_id))
        if row is None:
            s.add(
                Match(
                    chapter_id=decision.chapter_id,
                    question_id=decision.question_id,
                    score=decision.score,
                    fit=decision.fit.value,
                    rationale=decision.rationale,
                    missing_concepts_json=decision.missing_concepts,
                )
            )
        else:
            row.score = decision.score
            row.fit = decision.fit.value
            row.rationale = decision.rationale
            row.missing_concepts_json = decision.missing_concepts
    console.print(
        f"[green]Match saved: chapter={decision.chapter_id} "
        f"question={decision.question_id} fit={decision.fit.value} score={decision.score:.2f}[/]"
    )


# ---------------------------------------------------------------------------
# generate-paper
# ---------------------------------------------------------------------------


def _select_question_ids(
    subject: str, chapter: str, match_threshold: float, include_partial: bool
) -> tuple[int, list[int]]:
    with session_scope() as s:
        chapter_row = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter)
        ).scalar_one_or_none()
        if chapter_row is None:
            raise typer.BadParameter(f"Chapter not found: {subject}/{chapter}")
        allowed = {"full"} | ({"partial"} if include_partial else set())
        rows = s.execute(
            select(Match.question_id, Match.score, Match.fit)
            .where(Match.chapter_id == chapter_row.id)
            .order_by(Match.score.desc())
        ).all()
        ids = [
            qid
            for qid, score, fit in rows
            if fit in allowed and score >= match_threshold
        ]
        return chapter_row.id, ids


@app.command("generate-paper")
def cmd_generate_paper(
    subject: Annotated[str, typer.Option("--subject")],
    chapter: Annotated[str, typer.Option("--chapter")],
    count: Annotated[int | None, typer.Option("--count", help="Cap number of questions")] = None,
    match_threshold: Annotated[float, typer.Option("--match-threshold")] = MATCH_THRESHOLD_DEFAULT,
    dedup_threshold: Annotated[float, typer.Option("--dedup-threshold")] = DEDUP_COSINE_DEFAULT,
    include_partial: Annotated[bool, typer.Option("--include-partial/--full-only")] = True,
) -> None:
    """Render the practice-paper PDF from matched questions."""

    init_db()
    _, ids = _select_question_ids(subject, chapter, match_threshold, include_partial)
    if not ids:
        console.print("[yellow]No matched questions. Run `match` and `save-match` first.[/]")
        raise typer.Exit(code=1)

    kept_ids = dedup_questions(ids, cosine_threshold=dedup_threshold)
    if count is not None:
        kept_ids = kept_ids[:count]

    with session_scope() as s:
        rows = list(s.execute(select(Question).where(Question.id.in_(kept_ids))).scalars())
        fit_by_qid: dict[int, str] = {}
        chapter_row = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter)
        ).scalar_one()
        matches = list(
            s.execute(
                select(Match).where(
                    Match.chapter_id == chapter_row.id,
                    Match.question_id.in_(kept_ids),
                )
            ).scalars()
        )
        for m in matches:
            fit_by_qid[m.question_id] = m.fit
        papers_by_id = {
            p.id: p
            for p in s.execute(
                select(Paper).where(Paper.id.in_({r.paper_id for r in rows}))
            ).scalars()
        }
        ordered = sorted(rows, key=lambda r: (r.marks, r.id))
        paper_qs: list[PaperQuestion] = []
        for i, r in enumerate(ordered, start=1):
            p = papers_by_id.get(r.paper_id)
            label = (
                f"{p.subject.title()} {p.year or ''} {p.paper_number or ''}".strip()
                if p
                else f"paper {r.paper_id}"
            )
            paper_qs.append(
                PaperQuestion(
                    display_number=i,
                    number=r.number,
                    stem=r.stem,
                    marks=r.marks,
                    sub_parts=r.sub_parts_json or [],
                    options=r.options_json,
                    figure_paths=list(r.figure_paths_json or []),
                    source_label=label,
                    fit=fit_by_qid.get(r.id, "full"),
                )
            )

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = output_dir() / f"practice_paper_{_slug(subject)}_{_slug(chapter)}_{ts}.pdf"
    build_practice_paper(subject=subject, chapter=chapter, questions=paper_qs, output_path=out)
    console.print(f"[green]Wrote {out} ({len(paper_qs)} questions)[/]")


# ---------------------------------------------------------------------------
# generate-solutions / save-solution / save-critic
# ---------------------------------------------------------------------------


@app.command("generate-solutions")
def cmd_generate_solutions(
    subject: Annotated[str, typer.Option("--subject")],
    chapter: Annotated[str, typer.Option("--chapter")],
    match_threshold: Annotated[float, typer.Option("--match-threshold")] = MATCH_THRESHOLD_DEFAULT,
    include_partial: Annotated[bool, typer.Option("--include-partial/--full-only")] = True,
) -> None:
    """Assemble the worked-solutions PDF from the agent's reconciled solver output."""

    init_db()
    _ensure_primed(subject, chapter)
    chapter_id, ids = _select_question_ids(subject, chapter, match_threshold, include_partial)
    if not ids:
        console.print("[yellow]No matched questions.[/]")
        raise typer.Exit(code=1)

    with session_scope() as s:
        sols = list(
            s.execute(
                select(Solution).where(
                    Solution.chapter_id == chapter_id, Solution.question_id.in_(ids)
                )
            ).scalars()
        )
        missing = set(ids) - {sol.question_id for sol in sols}
        if missing:
            body_lines = [
                f"{len(missing)} questions still need solver output. For each question id below:",
                "  1. Read the question stem + figure paths in the DB via `igcse show-question <id>`.",
                "  2. Use prompt `prompts/solver.md` with the chapter profile.",
                "  3. Return JSON matching `SolverOutput`.",
                "  4. Save via: `igcse save-solution -` (stdin).",
                "  5. Then run a separate turn with `prompts/critic.md` for the SAME question,",
                "     return JSON matching `CriticOutput`, save via: `igcse save-critic -`.",
                "",
                "Pending question ids: " + ", ".join(str(i) for i in sorted(missing)),
            ]
            _print_agent_instructions("produce solver + critic", "\n".join(body_lines))
            console.print("[yellow]Rerun `generate-solutions` once all agent turns are saved.[/]")
            raise typer.Exit(code=1)

        disagreements = sum(1 for sol in sols if sol.critic_agrees is False)
        rate = disagreements / max(1, len(sols))
        if rate > CRITIC_DISAGREEMENT_BLOCK_RATE:
            console.print(
                f"[red]Critic disagreement rate {rate:.0%} > "
                f"{CRITIC_DISAGREEMENT_BLOCK_RATE:.0%}. "
                "Review flagged solutions before rebuilding the PDF.[/]"
            )
            raise typer.Exit(code=3)

        entries: list[SolutionEntry] = []
        qid_to_q = {
            q.id: q
            for q in s.execute(select(Question).where(Question.id.in_(ids))).scalars()
        }
        papers = {
            p.id: p
            for p in s.execute(
                select(Paper).where(
                    Paper.id.in_({q.paper_id for q in qid_to_q.values()})
                )
            ).scalars()
        }
        for i, sol in enumerate(sols, start=1):
            q = qid_to_q.get(sol.question_id)
            if q is None:
                continue
            solver = SolverOutput.model_validate(sol.reconciled_json or sol.solver_json)
            p = papers.get(q.paper_id)
            label = (
                f"{p.subject.title()} {p.year or ''} {p.paper_number or ''}".strip()
                if p
                else f"paper {q.paper_id}"
            )
            entries.append(
                SolutionEntry(
                    display_number=i,
                    number=q.number,
                    stem=q.stem,
                    figure_paths=list(q.figure_paths_json or []),
                    source_label=label,
                    out_of_scope=solver.out_of_scope,
                    missing=solver.missing,
                    final_answer=solver.final_answer,
                    steps=[step.model_dump() for step in solver.steps],
                    chapter_refs=solver.chapter_refs,
                )
            )

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = output_dir() / f"solutions_{_slug(subject)}_{_slug(chapter)}_{ts}.pdf"
    build_solutions_pdf(subject=subject, chapter=chapter, solutions=entries, output_path=out)
    console.print(f"[green]Wrote {out} ({len(entries)} solutions)[/]")


@app.command("save-solution")
def cmd_save_solution(
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist one SolverOutput row (per question + chapter)."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        solver = SolverOutput.model_validate(raw)
    except ValidationError as e:
        add_review("solver", "", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e
    with session_scope() as s:
        row = s.get(Solution, (solver.question_id, solver.chapter_id))
        if row is None:
            s.add(
                Solution(
                    question_id=solver.question_id,
                    chapter_id=solver.chapter_id,
                    solver_json=solver.model_dump(),
                    out_of_scope=solver.out_of_scope,
                )
            )
        else:
            row.solver_json = solver.model_dump()
            row.out_of_scope = solver.out_of_scope
            row.critic_json = None
            row.reconciled_json = None
            row.critic_agrees = True
    console.print(
        f"[green]Solver saved: q={solver.question_id} ch={solver.chapter_id} "
        f"oos={solver.out_of_scope}[/]"
    )


@app.command("save-critic")
def cmd_save_critic(
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist one CriticOutput and reconcile against the solver."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        critic = CriticOutput.model_validate(raw)
    except ValidationError as e:
        add_review("critic", "", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e

    with session_scope() as s:
        row = s.get(Solution, (critic.question_id, critic.chapter_id))
        if row is None:
            raise typer.BadParameter(
                f"No solver output yet for q={critic.question_id} ch={critic.chapter_id}. "
                "Save the solver output first."
            )
        row.critic_json = critic.model_dump()
        row.critic_agrees = critic.agrees
        if critic.agrees:
            row.reconciled_json = row.solver_json
        else:
            add_review(
                "critic_disagreement",
                f"q={critic.question_id} ch={critic.chapter_id}",
                "; ".join(critic.issues) or "critic disagreed without explicit issues",
                json.dumps(row.solver_json),
            )
    if critic.agrees:
        console.print(
            f"[green]Critic agreed: q={critic.question_id} ch={critic.chapter_id}[/]"
        )
    else:
        console.print(
            f"[yellow]Critic disagreed: q={critic.question_id} ch={critic.chapter_id} "
            f"issues={len(critic.issues)}[/]"
        )


@app.command("show-question")
def cmd_show_question(question_id: Annotated[int, typer.Argument()]) -> None:
    """Print a question's stem, options, sub-parts, source page, and figure paths."""

    init_db()
    with session_scope() as s:
        q = s.get(Question, question_id)
        if q is None:
            raise typer.BadParameter(f"No question with id {question_id}")
        page = s.get(Page, q.page_id) if q.page_id else None
        data = {
            "id": q.id,
            "paper_id": q.paper_id,
            "page_idx": page.idx if page else None,
            "page_png_path": page.png_path if page else None,
            "number": q.number,
            "type": q.type,
            "marks": q.marks,
            "stem": q.stem,
            "sub_parts": q.sub_parts_json,
            "options": q.options_json,
            "figure_paths": q.figure_paths_json,
            "figure_bboxes": q.figure_bboxes_json,
        }
    console.print_json(data=data)


@app.command("attach-figure-bbox")
def cmd_attach_figure_bbox(
    question_id: Annotated[int, typer.Option("--question-id")],
    paper_id: Annotated[int, typer.Option("--paper-id")],
    page_idx: Annotated[int, typer.Option("--page-idx")],
    bbox: Annotated[
        str,
        typer.Option(
            "--bbox",
            help='JSON object with normalized 0..1 coords, e.g. \'{"x":0.05,"y":0.10,"w":0.90,"h":0.40}\'',
        ),
    ],
    label: Annotated[
        str | None,
        typer.Option(
            "--label",
            help="Optional label for the crop file (e.g. 'main', 'continued'); appended to the filename",
        ),
    ] = None,
) -> None:
    """Crop a region of a paper's page PNG and attach it to the question's figures.

    Use this to embed original diagrams/tables/apparatus from the source past paper
    into the practice paper and solutions PDFs. Bbox is in normalized coords
    (0..1) relative to the page PNG, origin top-left.

    Multiple calls append additional crops to the same question (useful for
    multi-page structured questions or questions with multiple distinct figures).
    """

    init_db()
    try:
        bbox_data = json.loads(bbox)
        bb = BoundingBox.model_validate(bbox_data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise typer.BadParameter(f"Invalid bbox: {e}") from e

    with session_scope() as s:
        page = s.execute(
            select(Page).where(Page.paper_id == paper_id, Page.idx == page_idx)
        ).scalar_one_or_none()
        if page is None:
            raise typer.BadParameter(
                f"No page paper_id={paper_id} page_idx={page_idx}"
            )
        q = s.get(Question, question_id)
        if q is None:
            raise typer.BadParameter(f"No question id={question_id}")

        existing_count = len(q.figure_paths_json or [])
        out_dir = (
            figures_cache_dir() / f"paper-{paper_id:06d}" / f"page-{page_idx:04d}"
        )
        suffix = f"-{label}" if label else ""
        basename = f"q{question_id:06d}-attach{existing_count:02d}{suffix}"
        crops = crop_bboxes_to_files(
            Path(page.png_path),
            [bb],
            out_dir,
            basename=basename,
        )
        if not crops:
            console.print(f"[yellow]No crop produced (degenerate bbox?){suffix}[/]")
            return
        new_paths = list(q.figure_paths_json or []) + [str(p) for p in crops]
        q.figure_paths_json = new_paths
        msg = (
            f"[green]Attached {len(crops)} crop to q={question_id} "
            f"(now {len(new_paths)} figure(s) total)[/]"
        )
    console.print(msg)


# ---------------------------------------------------------------------------
# build-simulator / save-rubric / deploy
# ---------------------------------------------------------------------------


@app.command("save-rubric")
def cmd_save_rubric(
    chapter_id: Annotated[int, typer.Option("--chapter-id")],
    payload: Annotated[str | None, typer.Argument(help="JSON file path, '-' for stdin, or inline JSON")] = "-",
) -> None:
    """Persist one QuestionRubric for (chapter_id, question)."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        rubric = QuestionRubric.model_validate(raw)
    except ValidationError as e:
        add_review("rubric", f"chapter_id={chapter_id}", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e
    with session_scope() as s:
        row = s.get(Rubric, (rubric.source_question_db_id, chapter_id))
        if row is None:
            s.add(
                Rubric(
                    question_id=rubric.source_question_db_id,
                    chapter_id=chapter_id,
                    rubric_json=rubric.model_dump(),
                )
            )
        else:
            row.rubric_json = rubric.model_dump()
    console.print(
        f"[green]Rubric saved: q={rubric.source_question_db_id} ch={chapter_id}[/]"
    )


@app.command("build-simulator")
def cmd_build_simulator(
    subject: Annotated[str, typer.Option("--subject")],
    chapter: Annotated[str, typer.Option("--chapter")],
    no_npm: Annotated[bool, typer.Option("--no-npm", help="Skip `npm run build`")] = False,
) -> None:
    """Bake per-chapter JSON and (optionally) build the simulator."""

    init_db()
    _ensure_primed(subject, chapter)
    path = bake_simulator_set(subject, chapter)
    console.print(f"[green]Wrote simulator set: {path}[/]")

    if no_npm:
        return
    sim_dir = path.parent.parent.parent
    if not (sim_dir / "package.json").exists():
        console.print(f"[yellow]No package.json at {sim_dir}; skipping build.[/]")
        return
    if shutil.which("npm") is None:
        console.print("[yellow]npm not on PATH; skipping build.[/]")
        return
    console.print("[cyan]Running npm run build ...[/]")
    r = subprocess.run(["npm", "run", "build"], cwd=sim_dir, check=False)
    if r.returncode != 0:
        console.print(f"[red]npm build failed (exit {r.returncode})[/]")
        raise typer.Exit(code=r.returncode)
    console.print(f"[green]Built {simulator_dist_dir()}[/]")


@app.command("deploy")
def cmd_deploy(
    branch: Annotated[str, typer.Option("--branch")] = "gh-pages",
    remote: Annotated[str, typer.Option("--remote")] = "origin",  # noqa: ARG001
) -> None:
    """Push the simulator build to the Pages branch (no-op if already pushed).

    Requires the repo to already be a git repo with the remote set up. The
    GitHub Actions workflow in ``.github/workflows/deploy-pages.yml`` is the
    primary deploy path for CI; this command is a manual escape hatch.
    """

    dist = simulator_dist_dir()
    if not dist.exists():
        console.print(f"[red]{dist} does not exist. Run `igcse build-simulator` first.[/]")
        raise typer.Exit(code=1)
    console.print(
        Panel.fit(
            f"To deploy, commit and push your simulator changes and let the CI "
            f"workflow publish to `{branch}`. The public URL is "
            f"`https://<user>.github.io/igcse-study-agent/`.\n\n"
            f"Manual alternative: use the `gh-pages` npm package or `git subtree`.",
            title="[bold cyan]DEPLOY[/]",
            border_style="cyan",
        )
    )


# ---------------------------------------------------------------------------
# Step 0: chapter-prime / save-priming
# ---------------------------------------------------------------------------


@app.command("chapter-prime")
def cmd_chapter_prime(
    subject: Annotated[str, typer.Option("--subject")],
    chapter: Annotated[str, typer.Option("--chapter")],
) -> None:
    """Print the slide manifest and instruct the agent to read every slide."""

    init_db()
    slides = _list_chapter_slides(subject, chapter)
    if not slides:
        raise typer.BadParameter(
            f"No slides found for {subject}/{chapter}. "
            "Save the chapter (igcse save-chapter --screenshots-dir ...) first or "
            "drop screenshots into chapters/<subject>/<chapter>/."
        )

    body = [
        f"Chapter: {subject} / {chapter}",
        f"Slide count: {len(slides)}",
        "",
        "You MUST read EVERY slide below in order using the Read tool",
        "BEFORE producing the chapter profile or any downstream output.",
        "",
        "After reading the last slide, return JSON matching `ChapterPriming`",
        "and save via:",
        f'  igcse save-priming --subject "{subject}" --chapter "{chapter}" -',
        "(use prompt: prompts/chapter_priming.md).",
        "",
        "Slides to read:",
    ]
    body.extend(f"  {i + 1:2d}. {p}" for i, p in enumerate(slides))
    _print_agent_instructions("Step 0 - chapter priming", "\n".join(body))


@app.command("save-priming")
def cmd_save_priming(
    subject: Annotated[str, typer.Option("--subject")],
    chapter: Annotated[str, typer.Option("--chapter")],
    payload: Annotated[
        str | None,
        typer.Argument(help="JSON file path, '-' for stdin, or inline JSON"),
    ] = "-",
) -> None:
    """Persist a ChapterPriming for subject/chapter (gates downstream commands)."""

    init_db()
    raw = _read_json_payload(payload)
    expected_slides = _list_chapter_slides(subject, chapter)
    expected_count = len(expected_slides)
    try:
        priming = ChapterPriming.model_validate(raw)
    except ValidationError as e:
        add_review("chapter_priming", f"{subject}/{chapter}", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e

    if priming.slide_count_read != expected_count:
        add_review(
            "chapter_priming",
            f"{subject}/{chapter}",
            f"count mismatch: agent claims {priming.slide_count_read} but folder has {expected_count}",
            json.dumps(raw),
        )
        console.print(
            f"[red]slide count mismatch (agent={priming.slide_count_read}, folder={expected_count}); "
            f"re-prime with all slides[/]"
        )
        raise typer.Exit(code=2)

    expected_set = {str(p.resolve()) for p in expected_slides}
    claimed_set = {str(Path(p).resolve()) for p in priming.slide_paths}
    missing = sorted(expected_set - claimed_set)
    if missing:
        add_review(
            "chapter_priming",
            f"{subject}/{chapter}",
            f"missing slides in priming: {missing[:3]}",
            json.dumps(raw),
        )
        console.print(f"[red]priming did not include {len(missing)} expected slides[/]")
        for m in missing[:5]:
            console.print(f"  missing: {m}")
        raise typer.Exit(code=2)

    with session_scope() as s:
        chapter_row = s.execute(
            select(Chapter).where(Chapter.subject == subject, Chapter.name == chapter)
        ).scalar_one_or_none()
        if chapter_row is None:
            raise typer.BadParameter(
                f"Chapter row not found for {subject}/{chapter}. Save chapter profile first."
            )
        chapter_row.priming_json = priming.model_dump()
        chapter_row.primed_at = datetime.now(UTC)
    console.print(
        f"[green]Primed {subject}/{chapter}: read {priming.slide_count_read} slides, "
        f"{len(priming.topics_covered)} topics covered[/]"
    )


# ---------------------------------------------------------------------------
# Step 3.5: audit-page / save-audit / audit-status
# ---------------------------------------------------------------------------


@app.command("audit-page")
def cmd_audit_page(
    paper_id: Annotated[int, typer.Option("--paper-id")],
    page_idx: Annotated[int, typer.Option("--page-idx")],
) -> None:
    """Print the auditor sub-agent prompt + saved questions for one page.

    The main agent then invokes the Cursor Task tool with subagent_type='explore',
    readonly=true, and the prompt below. The subagent's final message is the
    ExtractionAudit JSON which the main agent passes to `igcse save-audit -`.
    """

    init_db()
    with session_scope() as s:
        page = s.execute(
            select(Page).where(Page.paper_id == paper_id, Page.idx == page_idx)
        ).scalar_one_or_none()
        if page is None:
            raise typer.BadParameter(f"No page idx={page_idx} for paper_id={paper_id}")
        questions = list(
            s.execute(
                select(Question).where(
                    Question.paper_id == paper_id, Question.page_id == page.id
                )
            ).scalars()
        )
        saved_payload = {
            "paper_id": paper_id,
            "page_idx": page_idx,
            "saved_questions": [
                {
                    "question_db_id": q.id,
                    "number": q.number,
                    "type": q.type,
                    "marks": q.marks,
                    "stem": q.stem,
                    "sub_parts": q.sub_parts_json or [],
                    "options": q.options_json,
                    "confidence": q.confidence,
                }
                for q in questions
            ],
        }
        png_path = page.png_path

    body_lines = [
        f"Auditor task for paper_id={paper_id} page_idx={page_idx}",
        "",
        "Invoke a Cursor Task subagent:",
        '  subagent_type: "explore"',
        "  readonly: true",
        f"  description: \"Audit page {paper_id}/{page_idx}\"",
        "  prompt: contents of prompts/audit_extraction.md, plus:",
        f"    page_png_path = {png_path}",
        f"    saved_questions_json = (the JSON below; {len(questions)} questions saved)",
        "",
        "After the subagent returns, save its ExtractionAudit JSON via:",
        f"  igcse save-audit --paper-id {paper_id} --page-idx {page_idx} -",
        "",
        "saved_questions_json:",
        json.dumps(saved_payload, indent=2),
    ]
    _print_agent_instructions("Step 3.5 - audit page", "\n".join(body_lines))


@app.command("save-audit")
def cmd_save_audit(
    paper_id: Annotated[int, typer.Option("--paper-id")],
    page_idx: Annotated[int, typer.Option("--page-idx")],
    payload: Annotated[
        str | None,
        typer.Argument(help="JSON file path, '-' for stdin, or inline JSON"),
    ] = "-",
) -> None:
    """Persist an ExtractionAudit; appends any missed questions to the page."""

    init_db()
    raw = _read_json_payload(payload)
    if isinstance(raw, dict):
        raw.setdefault("paper_id", paper_id)
        raw.setdefault("page_idx", page_idx)
    try:
        audit = ExtractionAudit.model_validate(raw)
    except ValidationError as e:
        add_review(
            "extraction_audit",
            f"paper_id={paper_id} page_idx={page_idx}",
            f"schema: {e}",
            json.dumps(raw),
        )
        raise typer.Exit(code=2) from e

    appended = 0
    cropped = 0
    with session_scope() as s:
        existing_iters = list(
            s.execute(
                select(ExtractionAuditRow).where(
                    ExtractionAuditRow.paper_id == paper_id,
                    ExtractionAuditRow.page_idx == page_idx,
                )
            ).scalars()
        )
        next_iter = (max((r.iteration for r in existing_iters), default=0)) + 1
        s.add(
            ExtractionAuditRow(
                paper_id=paper_id,
                page_idx=page_idx,
                iteration=next_iter,
                audit_json=audit.model_dump(),
                complete=audit.complete,
            )
        )
        page = s.execute(
            select(Page).where(Page.paper_id == paper_id, Page.idx == page_idx)
        ).scalar_one_or_none()
        if page is None:
            raise typer.BadParameter(
                f"page idx={page_idx} for paper_id={paper_id} not found"
            )
        for mq in audit.missed_questions:
            row = Question(
                paper_id=paper_id,
                page_id=page.id,
                number=mq.number,
                type=mq.type.value,
                marks=mq.marks,
                stem=mq.stem,
                sub_parts_json=[sp.model_dump() for sp in mq.sub_parts],
                options_json=[o.model_dump() for o in mq.options] if mq.options else None,
                figure_paths_json=[],
                figure_bboxes_json=[bb.model_dump() for bb in mq.figure_bboxes],
                confidence=mq.confidence,
                notes=(mq.notes or "") + " [appended by auditor]",
            )
            s.add(row)
            appended += 1

        # Materialize figure crops only when the auditor declares the page complete.
        # This is the figure-bleed-through guard from v3 Part A.
        if audit.complete:
            from agent.store.schemas import BoundingBox

            page_png = Path(page.png_path)
            qs_on_page = list(
                s.execute(
                    select(Question).where(
                        Question.paper_id == paper_id, Question.page_id == page.id
                    )
                ).scalars()
            )
            for qi, q in enumerate(qs_on_page):
                if q.figure_paths_json or not q.figure_bboxes_json:
                    continue
                fig_dir = figures_cache_dir() / f"paper-{paper_id:06d}" / f"page-{page_idx:04d}"
                bboxes = [BoundingBox.model_validate(bb) for bb in q.figure_bboxes_json]
                crops = crop_bboxes_to_files(
                    page_png,
                    bboxes,
                    fig_dir,
                    basename=f"q{qi:02d}",
                )
                if crops:
                    q.figure_paths_json = [str(p) for p in crops]
                    cropped += len(crops)

    console.print(
        f"[green]Audit saved (iteration {next_iter}): paper={paper_id} page={page_idx} "
        f"complete={audit.complete} missed={len(audit.missed_questions)} "
        f"misextractions={len(audit.misextractions)} appended={appended} "
        f"crops_materialized={cropped}[/]"
    )


@app.command("audit-status")
def cmd_audit_status(
    paper_id: Annotated[int | None, typer.Option("--paper-id")] = None,
) -> None:
    """Show audit coverage per page (paper-id optional filter)."""

    init_db()
    with session_scope() as s:
        if paper_id is None:
            rows = list(s.execute(select(ExtractionAuditRow)).scalars())
        else:
            rows = list(
                s.execute(
                    select(ExtractionAuditRow).where(ExtractionAuditRow.paper_id == paper_id)
                ).scalars()
            )
    t = RichTable(title=f"Audit coverage{f' (paper {paper_id})' if paper_id else ''}")
    t.add_column("paper")
    t.add_column("page")
    t.add_column("iter")
    t.add_column("complete")
    t.add_column("missed")
    t.add_column("misextract")
    for r in sorted(rows, key=lambda x: (x.paper_id, x.page_idx, x.iteration)):
        a = r.audit_json or {}
        missed_raw = a.get("missed_questions", [])
        misex_raw = a.get("misextractions", [])
        missed_n = len(missed_raw) if isinstance(missed_raw, list) else 0
        misex_n = len(misex_raw) if isinstance(misex_raw, list) else 0
        t.add_row(
            str(r.paper_id),
            str(r.page_idx),
            str(r.iteration),
            "yes" if r.complete else "no",
            str(missed_n),
            str(misex_n),
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Step 5.5: save-judge / save-improvement / solution-status
# ---------------------------------------------------------------------------


@app.command("save-judge")
def cmd_save_judge(
    payload: Annotated[
        str | None,
        typer.Argument(help="JSON file path, '-' for stdin, or inline JSON"),
    ] = "-",
) -> None:
    """Persist a JudgeReport for one solution; updates final_quality_score."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        judge = JudgeReport.model_validate(raw)
    except ValidationError as e:
        add_review("judge", "", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e

    with session_scope() as s:
        sol = s.get(Solution, (judge.question_id, judge.chapter_id))
        if sol is None:
            raise typer.BadParameter(
                f"No solution for q={judge.question_id} ch={judge.chapter_id}"
            )
        sol.judge_json = judge.model_dump()
        sol.judge_quality_score = judge.quality_score
        sol.iteration_count = judge.iteration
        prior = sol.final_quality_score or 0.0
        sol.final_quality_score = max(prior, judge.quality_score)
    msg = (
        f"q={judge.question_id} ch={judge.chapter_id} "
        f"iter={judge.iteration} score={judge.quality_score:.2f} "
        f"rewrite={'yes' if judge.rewrite_required else 'no'}"
    )
    if judge.rewrite_required:
        console.print(f"[yellow]Judge requests rewrite: {msg}[/]")
    else:
        console.print(f"[green]Judge approved: {msg}[/]")


@app.command("save-improvement")
def cmd_save_improvement(
    payload: Annotated[
        str | None,
        typer.Argument(help="JSON file path, '-' for stdin, or inline JSON"),
    ] = "-",
) -> None:
    """Replace solver output with an improved version; clears critic & judge."""

    init_db()
    raw = _read_json_payload(payload)
    try:
        solver = SolverOutput.model_validate(raw)
    except ValidationError as e:
        add_review("improved_solver", "", f"schema: {e}", json.dumps(raw))
        raise typer.Exit(code=2) from e
    with session_scope() as s:
        sol = s.get(Solution, (solver.question_id, solver.chapter_id))
        if sol is None:
            raise typer.BadParameter(
                f"No solution for q={solver.question_id} ch={solver.chapter_id}"
            )
        sol.solver_json = solver.model_dump()
        sol.out_of_scope = solver.out_of_scope
        sol.critic_json = None
        sol.reconciled_json = None
        sol.critic_agrees = True
        sol.judge_json = None
        sol.judge_quality_score = None
        sol.iteration_count = (sol.iteration_count or 1) + 1
    console.print(
        f"[cyan]Improvement saved: q={solver.question_id} ch={solver.chapter_id} "
        f"iter={sol.iteration_count}; rerun critic + judge[/]"
    )


@app.command("solution-status")
def cmd_solution_status(
    chapter_id: Annotated[int | None, typer.Option("--chapter-id")] = None,
) -> None:
    """Print the iteration history & quality score for solutions in a chapter."""

    init_db()
    with session_scope() as s:
        if chapter_id is None:
            sols = list(s.execute(select(Solution)).scalars())
        else:
            sols = list(
                s.execute(
                    select(Solution).where(Solution.chapter_id == chapter_id)
                ).scalars()
            )
    t = RichTable(title=f"Solution status{f' (chapter {chapter_id})' if chapter_id else ''}")
    t.add_column("q")
    t.add_column("ch")
    t.add_column("iter")
    t.add_column("critic")
    t.add_column("judge_q")
    t.add_column("final_q")
    t.add_column("oos")
    for sol in sols:
        t.add_row(
            str(sol.question_id),
            str(sol.chapter_id),
            str(sol.iteration_count or 1),
            "ok" if sol.critic_agrees else "disagree",
            f"{sol.judge_quality_score:.2f}" if sol.judge_quality_score is not None else "-",
            f"{sol.final_quality_score:.2f}" if sol.final_quality_score is not None else "-",
            "yes" if sol.out_of_scope else "no",
        )
    console.print(t)


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------


@app.command("review")
def cmd_review(
    resolve_id: Annotated[int | None, typer.Option("--resolve")] = None,
    show_all: Annotated[bool, typer.Option("--all", help="Show resolved too")] = False,
) -> None:
    """List (and optionally resolve) items in the review queue."""

    init_db()
    if resolve_id is not None:
        ok = resolve(resolve_id)
        console.print(
            f"[green]Resolved {resolve_id}[/]" if ok else f"[red]No review item {resolve_id}[/]"
        )
        return
    items = list_pending()
    _ = show_all  # reserved for future --all toggle when resolved items exist
    t = RichTable(title="Review queue")
    t.add_column("id")
    t.add_column("kind")
    t.add_column("ref")
    t.add_column("reason")
    t.add_column("created_at")
    for it in items:
        t.add_row(
            str(it.id),
            it.kind,
            it.ref,
            it.reason[:80],
            it.created_at.isoformat(timespec="seconds") if it.created_at else "",
        )
    console.print(t)


@app.command("dashboard")
def cmd_dashboard(
    output: Annotated[
        Path,
        typer.Option("--output", help="Write markdown dashboard here"),
    ] = Path("QUALITY_DASHBOARD.md"),
) -> None:
    """Write a per-run markdown dashboard summarizing pipeline health."""

    from datetime import datetime

    init_db()
    with session_scope() as s:
        papers = list(s.execute(select(Paper)).scalars())
        questions = list(s.execute(select(Question)).scalars())
        chapters = list(s.execute(select(Chapter)).scalars())
        matches = list(s.execute(select(Match)).scalars())
        solutions = list(s.execute(select(Solution)).scalars())
        rubrics = list(s.execute(select(Rubric)).scalars())
        pending = list_pending()

    n_low_conf = sum(1 for q in questions if q.confidence < LOW_CONFIDENCE_THRESHOLD)
    n_full = sum(1 for m in matches if m.fit == "full")
    n_partial = sum(1 for m in matches if m.fit == "partial")
    n_none = sum(1 for m in matches if m.fit == "none")
    n_critic_disagree = sum(1 for sol in solutions if not sol.critic_agrees)
    n_oos = sum(1 for sol in solutions if sol.out_of_scope)

    lines = [
        "# IGCSE study agent — quality dashboard",
        "",
        f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
        "",
        "## Corpus",
        "",
        f"- Papers ingested: **{len(papers)}**",
        f"- Questions extracted: **{len(questions)}**",
        f"- Low-confidence questions (<{LOW_CONFIDENCE_THRESHOLD:.2f}): "
        f"**{n_low_conf}** ({n_low_conf / max(1, len(questions)):.0%})",
        "",
        "## Chapters",
        "",
        f"- Chapter profiles: **{len(chapters)}**",
        "",
        "## Matching",
        "",
        f"- Full matches: **{n_full}**",
        f"- Partial matches: **{n_partial}**",
        f"- Not matched: **{n_none}**",
        "",
        "## Solutions",
        "",
        f"- Solver outputs saved: **{len(solutions)}**",
        f"- Out-of-scope flagged: **{n_oos}**",
        f"- Critic disagreements: **{n_critic_disagree}** "
        f"({n_critic_disagree / max(1, len(solutions)):.0%})",
        "",
        "## Simulator",
        "",
        f"- Rubrics generated: **{len(rubrics)}**",
        f"- Sets directory: `{simulator_sets_dir()}`",
        "",
        "## Review queue",
        "",
        f"- Pending items: **{len(pending)}**",
    ]
    if pending:
        lines.append("")
        lines.append("| id | kind | ref | reason |")
        lines.append("|---:|---|---|---|")
        for it in pending[:20]:
            reason = (it.reason or "").replace("|", "\\|")[:80]
            lines.append(f"| {it.id} | {it.kind} | {it.ref} | {reason} |")
        if len(pending) > 20:
            lines.append(f"\n... and {len(pending) - 20} more")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Wrote {output}[/]")


@app.command("status")
def cmd_status() -> None:
    """Print a one-screen dashboard of corpus and pipeline state."""

    init_db()
    with session_scope() as s:
        n_papers = s.execute(select(Paper)).scalars().unique().all()
        n_questions = s.execute(select(Question)).scalars().unique().all()
        n_chapters = s.execute(select(Chapter)).scalars().unique().all()
        n_matches = s.execute(select(Match)).scalars().unique().all()
        n_solutions = s.execute(select(Solution)).scalars().unique().all()
        n_rubrics = s.execute(select(Rubric)).scalars().unique().all()
    t = RichTable(title="IGCSE study agent: status")
    t.add_column("metric")
    t.add_column("count", justify="right")
    t.add_row("papers", str(len(n_papers)))
    t.add_row("pages-rendered", str(sum(len(p.pages) for p in n_papers)))
    t.add_row("questions", str(len(n_questions)))
    t.add_row("chapters", str(len(n_chapters)))
    t.add_row("matches", str(len(n_matches)))
    t.add_row("solutions", str(len(n_solutions)))
    t.add_row("rubrics", str(len(n_rubrics)))
    t.add_row("pages-cache", str(pages_cache_dir()))
    t.add_row("figures-cache", str(figures_cache_dir()))
    t.add_row("sets-dir", str(simulator_sets_dir()))
    console.print(t)


if __name__ == "__main__":
    app()
