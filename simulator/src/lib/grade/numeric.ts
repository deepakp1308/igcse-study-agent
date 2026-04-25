import type { RubricPart } from "../../types";

export interface NumericResult {
  parsed: number | null;
  unit: string | null;
  expected: number | null;
  tolerance_pct: number | null;
  within_tolerance: boolean;
  unit_ok: boolean;
  off_by_magnitude: number | null;
}

const NUMBER_RE = /(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)/g;

export function parseNumericAnswer(raw: string | number | null | undefined): {
  value: number | null;
  unit: string | null;
} {
  if (raw == null || raw === "") return { value: null, unit: null };
  if (typeof raw === "number") return { value: raw, unit: null };
  const cleaned = String(raw).trim();
  // Prefer the LAST number in the string - students often show working like
  // "n = m/M = 10 / 40 = 0.25 mol" where the final number is the answer.
  const matches = [...cleaned.matchAll(NUMBER_RE)];
  if (matches.length === 0) return { value: null, unit: null };
  const last = matches[matches.length - 1];
  const v = Number.parseFloat(last[1]);
  if (!Number.isFinite(v)) return { value: null, unit: null };
  const rest = cleaned.slice((last.index ?? 0) + last[1].length).trim();
  return { value: v, unit: rest || null };
}

export function gradeNumeric(
  part: RubricPart,
  student: { value?: number | null; unit?: string | null; text?: string | null },
): NumericResult {
  let parsed: number | null = null;
  let unit: string | null = null;

  if (student.value != null) {
    parsed = student.value;
    unit = student.unit ?? null;
  } else if (student.text != null) {
    const p = parseNumericAnswer(student.text);
    parsed = p.value;
    unit = p.unit;
  }

  const expected = part.numeric_answer ?? null;
  const tol = part.numeric_tolerance_pct ?? null;
  if (expected == null || parsed == null) {
    return {
      parsed,
      unit,
      expected,
      tolerance_pct: tol,
      within_tolerance: false,
      unit_ok: false,
      off_by_magnitude: null,
    };
  }
  const absTol = (Math.abs(expected) * (tol ?? 0)) / 100 || 1e-9;
  const within = Math.abs(parsed - expected) <= absTol;

  const unitOk = part.numeric_unit
    ? unit
      ? unit.toLowerCase().replace(/\s+/g, "") ===
        part.numeric_unit.toLowerCase().replace(/\s+/g, "")
      : false
    : true;

  // off-by-magnitude detection (x10, x100, x0.1, etc.)
  let offBy: number | null = null;
  if (!within && parsed !== 0 && expected !== 0) {
    const ratio = parsed / expected;
    const closeToPow10 = (r: number, tolerance = 0.05) => {
      const log = Math.log10(Math.abs(r));
      const rounded = Math.round(log);
      return Math.abs(log - rounded) < tolerance && rounded !== 0;
    };
    if (closeToPow10(ratio)) {
      offBy = Math.pow(10, Math.round(Math.log10(Math.abs(ratio))));
    }
  }

  return {
    parsed,
    unit,
    expected,
    tolerance_pct: tol,
    within_tolerance: within,
    unit_ok: unitOk,
    off_by_magnitude: offBy,
  };
}
