"""Build the worked-solutions PDF.

Consumes reconciled solver JSON produced by the Cursor agent (schema
``SolverOutput``) and lays it out as a study companion with chapter
citations and out-of-scope banners where applicable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image as RLImage,
)
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


@dataclass
class SolutionEntry:
    display_number: int
    number: str
    stem: str
    figure_paths: list[str]
    source_label: str
    out_of_scope: bool
    missing: list[str]
    final_answer: str | None
    steps: list[dict[str, object]]  # {number, explanation, chapter_ref}
    chapter_refs: list[str]


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=20, spaceAfter=8),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=11, textColor=colors.grey, spaceAfter=12
        ),
        "qhead": ParagraphStyle(
            "qhead", parent=base["Heading3"], fontSize=12, spaceBefore=10, spaceAfter=4
        ),
        "stem": ParagraphStyle(
            "stem", parent=base["Normal"], fontSize=11, leading=14, spaceAfter=6
        ),
        "step": ParagraphStyle(
            "step",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            leftIndent=16,
            spaceAfter=3,
        ),
        "answer": ParagraphStyle(
            "answer",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.darkgreen,
            spaceAfter=4,
        ),
        "cref": ParagraphStyle(
            "cref", parent=base["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=8
        ),
        "oos": ParagraphStyle(
            "oos",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.red,
            backColor=colors.mistyrose,
            borderPadding=4,
            spaceAfter=8,
        ),
        "meta": ParagraphStyle("meta", parent=base["Normal"], fontSize=9, textColor=colors.grey),
    }


def _inline_image(path: Path, max_width_cm: float = 16.0) -> RLImage | None:
    """Render a figure crop inline, full text-width, preserving aspect ratio."""
    if not path.exists():
        return None
    try:
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return None
    if w == 0 or h == 0:
        return None
    target_w = max_width_cm * cm
    target_h = target_w * (h / w)
    if target_h > 22 * cm:
        target_h = 22 * cm
        target_w = target_h * (w / h)
    img = RLImage(str(path), width=target_w, height=target_h)
    img.hAlign = "LEFT"
    return img


def _final_answer_box(text: str) -> Table:
    t = Table([[f"Final answer: {text}"]], colWidths=[16 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.darkgreen),
                ("BACKGROUND", (0, 0), (-1, -1), colors.honeydew),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.darkgreen),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def build_solutions_pdf(
    subject: str,
    chapter: str,
    solutions: list[SolutionEntry],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"IGCSE Worked Solutions - {subject} - {chapter}",
    )

    story: list[object] = []
    story.append(Paragraph(f"{subject.title()}: {chapter}", styles["title"]))
    story.append(Paragraph("IGCSE Worked Solutions", styles["subtitle"]))
    story.append(
        Paragraph(
            "Each answer below is written using only the concepts taught in this chapter. "
            "If a question needs material beyond the chapter, it is flagged for teacher review.",
            styles["meta"],
        )
    )
    story.append(PageBreak())

    for entry in solutions:
        story.append(
            Paragraph(
                f"<b>Question {entry.display_number}.</b> &nbsp;"
                f"<font color='grey' size='9'>[{entry.source_label}]</font>",
                styles["qhead"],
            )
        )
        valid_figs = [Path(f) for f in entry.figure_paths if Path(f).exists()]
        if valid_figs:
            # Figure crops show the original printed question (stem + diagrams +
            # tables + options as in the past paper) so the student can see
            # exactly which question this solution belongs to.
            for fig in valid_figs:
                img = _inline_image(fig)
                if img is not None:
                    story.append(img)
                    story.append(Spacer(1, 3 * mm))
        elif entry.stem:
            # Fallback: paraphrased stem when no crop is attached.
            story.append(Paragraph(entry.stem, styles["stem"]))

        if entry.out_of_scope:
            missing_html = (
                "<br/>Missing: " + ", ".join(entry.missing) if entry.missing else ""
            )
            story.append(
                Paragraph(
                    "<b>Review with teacher.</b> This question reaches beyond the "
                    "current chapter." + missing_html,
                    styles["oos"],
                )
            )
            story.append(Spacer(1, 4 * mm))
            continue

        if entry.final_answer:
            story.append(_final_answer_box(entry.final_answer))
            story.append(Spacer(1, 2 * mm))

        for step in entry.steps:
            if not isinstance(step, dict):
                continue
            number = step.get("number", "")
            explanation = step.get("explanation", "")
            chapter_ref = step.get("chapter_ref") or ""
            suffix = (
                f" <font color='grey' size='9'>[from: {chapter_ref}]</font>"
                if chapter_ref
                else ""
            )
            story.append(Paragraph(f"<b>{number}.</b> {explanation}{suffix}", styles["step"]))

        if entry.chapter_refs:
            story.append(
                Paragraph(
                    "From your chapter: " + "; ".join(entry.chapter_refs),
                    styles["cref"],
                )
            )
        story.append(Spacer(1, 4 * mm))

    story.append(PageBreak())
    story.append(
        Paragraph(
            f"Generated {datetime.now(UTC).isoformat(timespec='seconds')}",
            styles["meta"],
        )
    )
    doc.build(story)
    return output_path
