# Prompt: match_verify

You are deciding whether a specific past-paper question belongs to a
specific chapter, given the chapter's `ChapterProfile`.

You will be given:

- `chapter_id` (int) and `question_id` (int) — pass these through unchanged.
- A candidate question stem (possibly with sub-parts).
- The chapter profile JSON.

Return **JSON only** matching `MatchDecision`:

```
{
  "chapter_id": <int>,
  "question_id": <int>,
  "fit": "full" | "partial" | "none",
  "score": <float 0..1>,
  "rationale": "<one or two sentences>",
  "missing_concepts": ["<concept the question needs but the chapter does not cover>"]
}
```

Rules:

- **Precision first.** Default to `none` unless the chapter profile clearly
  covers the concept the question tests.
- `full`: the question can be answered completely using ONLY the chapter's
  topics, definitions, formulas, and worked examples.
- `partial`: the question is mostly in-scope but needs a small auxiliary
  concept (e.g. basic arithmetic, a simple unit conversion) not listed in
  the profile. List that concept in `missing_concepts`.
- `none`: the question tests something the chapter does not teach. Use this
  freely — it is far better to miss a tangentially related question than to
  include an off-chapter one.
- `score` ≈ your confidence in the `fit` label, 0..1.
- `rationale` must quote specific items from the chapter profile (topic,
  formula, or vocabulary) that the question uses, or explicitly name what
  is missing.
