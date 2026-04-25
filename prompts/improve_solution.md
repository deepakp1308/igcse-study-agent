# Prompt: improve_solution (in-session turn)

You are revising a worked solution based on a strict tutor's
feedback (see `JudgeReport`). Your job is to produce a new
`SolverOutput` JSON that addresses every issue in the `improvement_brief`
while still using ONLY concepts from the chapter profile.

You will be given:

- `question_id` and `chapter_id`.
- The question (stem, sub-parts).
- The chapter profile JSON.
- The previous `SolverOutput` (full).
- The `JudgeReport` (especially `issues` and `improvement_brief`).

Steps:

1. Read each issue in `JudgeReport.issues`. Treat `severity: high` as
   non-negotiable.
2. Re-derive the answer if necessary. Keep arithmetic correct. Keep every
   step inside the chapter scope.
3. Rewrite using language a motivated 15-year-old can follow:
   - Introduce technical terms with a plain-English gloss the first time
     they appear (e.g. "the cathode (the negative electrode)").
   - Show every substitution, not just the final calculation.
   - State units explicitly.
4. Return a single JSON object matching `SolverOutput`:

```
{
  "question_id": <int>,
  "chapter_id": <int>,
  "out_of_scope": <bool>,
  "missing": [],
  "final_answer": "<single-line plain-text answer>",
  "steps": [
    { "number": 1, "explanation": "...", "chapter_ref": "<topic/formula used>" }
  ],
  "chapter_refs": ["<all profile items relied on, deduplicated>"]
}
```

Rules:

- Same chapter rules as `solver.md`: every step's `chapter_ref` must map
  to something in the chapter profile. If a fix would push you outside
  scope, say so explicitly with `out_of_scope: true` and `missing: [...]`.
- Save the result with `igcse save-improvement -`. That CLI clears the
  critic and judge slots so they re-run on the new content.
- Do NOT change `question_id` or `chapter_id`.
- Aim for a clearly higher quality_score on the next judge pass. If you
  fully address the brief, you should expect a score above 0.85.
