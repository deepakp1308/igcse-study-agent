"""PDF rendering pipeline tests using a synthesized PDF fixture."""

from __future__ import annotations

from pathlib import Path

import fitz

from agent.ingest.render import (
    guess_subject_from_path,
    ingest_papers_folder,
    render_pdf_pages,
    sha256_file,
)


def _make_pdf(path: Path, pages: int = 2) -> None:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 120), f"Page {i + 1}: Q{i + 1}. What is 2+{i}?", fontsize=14)
    doc.save(str(path))
    doc.close()


def test_render_pdf_pages(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf(pdf, pages=3)
    out_dir = tmp_path / "pages"
    paths = render_pdf_pages(pdf, out_dir)
    assert len(paths) == 3
    assert all(p.exists() for p in paths)
    assert all(p.suffix == ".png" for p in paths)


def test_render_is_idempotent(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf(pdf, pages=1)
    out_dir = tmp_path / "pages"
    render_pdf_pages(pdf, out_dir)
    t0 = (out_dir / "page-0000.png").stat().st_mtime
    render_pdf_pages(pdf, out_dir)
    t1 = (out_dir / "page-0000.png").stat().st_mtime
    assert t0 == t1


def test_sha256_file(tmp_path: Path):
    pdf = tmp_path / "paper.pdf"
    _make_pdf(pdf, pages=1)
    h1 = sha256_file(pdf)
    h2 = sha256_file(pdf)
    assert h1 == h2
    assert len(h1) == 64


def test_guess_subject_from_path(tmp_path: Path):
    root = tmp_path / "papers"
    (root / "chemistry").mkdir(parents=True)
    pdf = root / "chemistry" / "0620_12.pdf"
    pdf.touch()
    assert guess_subject_from_path(pdf, root) == "chemistry"
    assert guess_subject_from_path(root / "loose.pdf", root) == "unknown"


def test_ingest_papers_folder(tmp_path: Path):
    root = tmp_path / "papers"
    (root / "chemistry").mkdir(parents=True)
    pdf = root / "chemistry" / "0620_12.pdf"
    _make_pdf(pdf, pages=2)
    results = ingest_papers_folder(root)
    assert len(results) == 1
    r = results[0]
    assert r.page_count == 2
    assert r.reused is False

    # Re-run: should reuse
    results2 = ingest_papers_folder(root)
    assert results2[0].reused is True
