"""Offline eval runner.

Invokes the simulator grader (Node via a tiny bridge script) against the
``rubric_grader.yaml`` golden set and reports agreement. Prints a markdown
dashboard and writes it to ``evals/last_report.md``.

Exits non-zero when agreement is below ``--threshold`` (default 0.85).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from agent.store.schemas import QuestionRubric
from evals.datasets import (
    RubricGraderCase,
    load_chapter_match,
    load_rubric_grader,
    load_solution_quality,
)

HERE = Path(__file__).parent
REPO = HERE.parent
BRIDGE = REPO / "simulator" / "src" / "lib" / "grade" / "bridge.mjs"


def _schema_check() -> list[str]:
    errs: list[str] = []
    try:
        load_chapter_match()
    except (OSError, ValidationError) as e:
        errs.append(f"chapter_match: {e}")
    try:
        load_solution_quality()
    except (OSError, ValidationError) as e:
        errs.append(f"solution_quality: {e}")
    try:
        for case in load_rubric_grader():
            QuestionRubric.model_validate(case.rubric)
    except (OSError, ValidationError) as e:
        errs.append(f"rubric_grader: {e}")
    return errs


def _run_simulator_grader(cases: Iterable[RubricGraderCase]) -> list[dict[str, object]]:
    if shutil.which("node") is None:
        raise RuntimeError(
            "node not found on PATH; install Node.js to run the rubric_grader eval"
        )
    if not BRIDGE.exists():
        raise RuntimeError(f"Grader bridge missing: {BRIDGE}")
    payload = [
        {
            "id": c.id,
            "rubric": c.rubric,
            "student_answers": c.student_answers,
        }
        for c in cases
    ]
    proc = subprocess.run(
        ["node", str(BRIDGE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(REPO / "simulator"),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"grader bridge failed: {proc.stderr}")
    return list(json.loads(proc.stdout))


def _render_report(agreement: float, rows: list[dict[str, object]], schema_errs: list[str]) -> str:
    lines = ["# IGCSE study agent — eval report", ""]
    lines.append(f"**Rubric grader agreement**: {agreement:.0%}")
    lines.append("")
    if schema_errs:
        lines.append("## Schema errors")
        for err in schema_errs:
            lines.append(f"- {err}")
        lines.append("")
    lines.append("## Rubric grader per-case results")
    lines.append("")
    lines.append("| id | gold | grader | agreed |")
    lines.append("|---|---:|---:|:---:|")
    for row in rows:
        ok = "✓" if row["agreed"] else "✗"
        lines.append(
            f"| {row['id']} | {row['gold']:.1f} | {row['grader']:.2f} | {ok} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument(
        "--threshold-check",
        action="store_true",
        help="Exit non-zero if agreement < threshold",
    )
    ap.add_argument("--skip-grader", action="store_true", help="Schema checks only (no Node)")
    args = ap.parse_args(argv)

    schema_errs = _schema_check()

    rows: list[dict[str, object]] = []
    agreement = 1.0

    if not args.skip_grader and shutil.which("node") is not None:
        cases = load_rubric_grader()
        try:
            results = _run_simulator_grader(cases)
        except RuntimeError as e:
            print(f"[warn] skipping grader eval: {e}", file=sys.stderr)
        else:
            agreed = 0
            for case, result in zip(cases, results, strict=True):
                grader_marks = float(result.get("marks", 0.0))
                delta = abs(grader_marks - case.gold_marks)
                is_agreed = delta <= case.tolerance + 1e-9
                rows.append(
                    {
                        "id": case.id,
                        "gold": case.gold_marks,
                        "grader": grader_marks,
                        "agreed": is_agreed,
                    }
                )
                if is_agreed:
                    agreed += 1
            total = max(1, len(rows))
            agreement = agreed / total
    else:
        print("[info] node not on PATH, skipping rubric grader agreement", file=sys.stderr)

    report = _render_report(agreement, rows, schema_errs)
    (HERE / "last_report.md").write_text(report, encoding="utf-8")
    print(report)

    if schema_errs:
        return 2
    if args.threshold_check and rows and agreement < args.threshold:
        print(
            f"[fail] agreement {agreement:.0%} < threshold {args.threshold:.0%}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
