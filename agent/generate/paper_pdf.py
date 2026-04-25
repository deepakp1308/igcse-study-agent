"""Build the practice-paper PDF (questions + answer spaces).

Pure layout code. Assumes ``questions`` are already filtered, ordered, and
de-duplicated by callers (the CLI ``generate-paper`` command).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
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

_TIME_PER_MARK_MIN = 1.2  # IGCSE rule-of-thumb


@dataclass
class PaperQuestion:
    display_number: int
    number: str
    stem: str
    marks: int
    sub_parts: list[dict[str, object]]
    options: list[dict[str, object]] | None
    figure_paths: list[str]
    source_label: str
    fit: str  # "full" | "partial"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontSize=20,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontSize=11,
            textColor=colors.grey,
            spaceAfter=12,
        ),
        "qhead": ParagraphStyle(
            "qhead",
            parent=base["Heading3"],
            fontSize=12,
            spaceBefore=10,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "stem": ParagraphStyle(
            "stem",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            spaceAfter=6,
        ),
        "sub": ParagraphStyle(
            "sub",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            leftIndent=18,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.grey,
        ),
        "warn": ParagraphStyle(
            "warn",
            parent=base["Normal"],
            fontSize=10,
            textColor=colors.darkorange,
            spaceAfter=6,
        ),
    }


def _answer_box(marks: int) -> Table:
    """Draw a blank answer box sized proportionally to marks."""

    height = max(1.5, 1.1 * max(1, marks)) * cm
    t = Table([[""]], colWidths=[16 * cm], rowHeights=[height])
    t.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _inline_image(path: Path, max_width_cm: float = 12.0) -> RLImage | None:
    if not path.exists():
        return None
    try:
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return None
    if w == 0 or h == 0:
        return None
    target_w = min(max_width_cm * cm, (w / h) * 10 * cm)
    target_h = target_w * (h / w)
    img = RLImage(str(path), width=target_w, height=target_h)
    img.hAlign = "LEFT"
    return img


def build_practice_paper(
    subject: str,
    chapter: str,
    questions: list[PaperQuestion],
    output_path: Path,
    include_partial: bool = True,
) -> Path:
    """Render the practice-paper PDF for the given chapter-selected questions."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"IGCSE Practice Paper - {subject} - {chapter}",
    )

    total_marks = sum(q.marks for q in questions)
    est_min = round(total_marks * _TIME_PER_MARK_MIN)

    story: list[object] = []
    story.append(Paragraph(f"{subject.title()}: {chapter}", styles["title"]))
    story.append(Paragraph("IGCSE Practice Paper", styles["subtitle"]))
    story.append(
        Paragraph(
            f"Total marks: {total_marks} &nbsp;&nbsp; Estimated time: {est_min} minutes "
            f"&nbsp;&nbsp; Questions: {len(questions)}",
            styles["meta"],
        )
    )
    story.append(Spacer(1, 6 * mm))
    if any(q.fit == "partial" for q in questions):
        story.append(
            Paragraph(
                "Note: questions marked with <b>*</b> may stretch slightly beyond "
                "this chapter. They are included for stretch practice.",
                styles["warn"],
            )
        )
    story.append(
        Paragraph(
            "Write your answers in the boxes provided. Show working where appropriate.",
            styles["meta"],
        )
    )
    story.append(PageBreak())

    for q in questions:
        if not include_partial and q.fit == "partial":
            continue
        star = " *" if q.fit == "partial" else ""
        story.append(
            Paragraph(
                f"<b>{q.display_number}.</b>{star} &nbsp;"
                f"<font color='grey' size='9'>[{q.marks} marks &nbsp;|&nbsp; {q.source_label}]</font>",
                styles["qhead"],
            )
        )
        if q.stem:
            story.append(Paragraph(q.stem, styles["stem"]))

        for fig in q.figure_paths:
            img = _inline_image(Path(fig))
            if img is not None:
                story.append(img)
                story.append(Spacer(1, 2 * mm))

        if q.options:
            for opt in q.options:
                if not isinstance(opt, dict):
                    continue
                label = opt.get("label", "")
                text = opt.get("text", "")
                story.append(
                    Paragraph(
                        f"<b>{label}.</b> &nbsp; {text}",
                        styles["sub"],
                    )
                )
            story.append(Spacer(1, 3 * mm))
            story.append(
                Paragraph(
                    "Answer: __________",
                    styles["sub"],
                )
            )
        elif q.sub_parts:
            for sp in q.sub_parts:
                if not isinstance(sp, dict):
                    continue
                label = str(sp.get("label", ""))
                prompt = str(sp.get("prompt", ""))
                raw_marks = sp.get("marks", 0)
                marks = int(raw_marks) if isinstance(raw_marks, int | float | str) else 0
                story.append(
                    Paragraph(
                        f"<b>({label})</b> {prompt} "
                        f"<font color='grey' size='9'>[{marks}]</font>",
                        styles["sub"],
                    )
                )
                story.append(_answer_box(marks if marks > 0 else 1))
                story.append(Spacer(1, 2 * mm))
        else:
            story.append(_answer_box(q.marks))

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
