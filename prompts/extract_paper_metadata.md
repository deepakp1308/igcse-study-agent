# Prompt: extract_paper_metadata

You are looking at the cover page of an IGCSE past paper.

Return **JSON only** (no prose, no code fences) matching this schema:

```
{
  "subject": "<chemistry | physics | biology | mathematics | english | french | ...>",
  "year": <int | null>,
  "session": "<e.g. 'May/June', 'Oct/Nov'; null if unclear>",
  "paper_number": "<e.g. '2', '4', '12'; null if unclear>",
  "tier": "core" | "extended" | "foundation" | "higher" | "unknown",
  "total_marks": <int | null>,
  "confidence": <float 0..1>
}
```

Guidance:

- `subject` must be lowercase.
- IGCSE Cambridge papers print the paper code like `0620/22` — `0620` implies
  Chemistry, `0625` Physics, `0610` Biology, `0580` Mathematics (Core/Extended
  indicated by paper number suffix). If unsure, set `subject: "unknown"` and
  lower `confidence`.
- Don't invent metadata. Missing is fine.
- `confidence` should reflect how sure you are of the **whole** metadata,
  not any single field.
