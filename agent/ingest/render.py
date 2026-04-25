"""Deterministic PDF ingestion: walk a folder, render pages to PNG, store rows.

No LLM calls here. The resulting PNGs + ``Paper``/``Page`` rows form the input
surface that the Cursor agent reads from in its own turn (via the Read tool
on the PNG paths).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from sqlalchemy import select

from agent.config import RENDER_DPI, pages_cache_dir
from agent.store.db import Page, Paper, session_scope

logger = logging.getLogger(__name__)


@dataclass
class RenderResult:
    paper_id: int
    path: Path
    hash: str
    page_count: int
    reused: bool


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_subject_from_path(pdf_path: Path, papers_root: Path) -> str:
    """Best-effort subject guess from folder structure under ``papers_root``.

    If the user organizes ``papers_root/<Subject>/*.pdf`` we use the immediate
    subfolder. Otherwise we return ``"unknown"`` and rely on the agent to
    correct via the cover-page metadata pass.
    """

    try:
        rel = pdf_path.relative_to(papers_root)
    except ValueError:
        return "unknown"
    if len(rel.parts) >= 2:
        return rel.parts[0].lower()
    return "unknown"


def render_pdf_pages(pdf_path: Path, out_dir: Path, dpi: int = RENDER_DPI) -> list[Path]:
    """Render every page of ``pdf_path`` to a PNG under ``out_dir``.

    Returns the list of rendered PNG paths in page order. Idempotent: if a PNG
    with the expected name already exists, it is reused.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    doc = fitz.open(pdf_path)
    try:
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        for idx, page in enumerate(doc):
            out = out_dir / f"page-{idx:04d}.png"
            if not out.exists():
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                pix.save(str(out))
            paths.append(out)
    finally:
        doc.close()
    return paths


def ingest_papers_folder(papers_root: Path) -> list[RenderResult]:
    """Walk ``papers_root`` for PDFs, render pages, upsert DB rows.

    Returns one ``RenderResult`` per PDF. Safe to re-run: unchanged files
    (same content hash) are skipped.
    """

    if not papers_root.exists():
        raise FileNotFoundError(f"Papers folder not found: {papers_root}")
    if not papers_root.is_dir():
        raise NotADirectoryError(f"Not a directory: {papers_root}")

    results: list[RenderResult] = []
    pdfs = sorted(papers_root.rglob("*.pdf"))
    logger.info("found %d PDFs under %s", len(pdfs), papers_root)

    for pdf in pdfs:
        file_hash = sha256_file(pdf)
        with session_scope() as s:
            existing = s.execute(select(Paper).where(Paper.hash == file_hash)).scalar_one_or_none()
            if existing is not None:
                results.append(
                    RenderResult(
                        paper_id=existing.id,
                        path=pdf,
                        hash=file_hash,
                        page_count=len(existing.pages),
                        reused=True,
                    )
                )
                continue

            paper = Paper(
                subject=guess_subject_from_path(pdf, papers_root),
                path=str(pdf),
                hash=file_hash,
            )
            s.add(paper)
            s.flush()

            paper_pages_dir = pages_cache_dir() / f"paper-{paper.id:06d}"
            png_paths = render_pdf_pages(pdf, paper_pages_dir)
            for idx, png in enumerate(png_paths):
                s.add(Page(paper_id=paper.id, idx=idx, png_path=str(png)))

            results.append(
                RenderResult(
                    paper_id=paper.id,
                    path=pdf,
                    hash=file_hash,
                    page_count=len(png_paths),
                    reused=False,
                )
            )
    return results
