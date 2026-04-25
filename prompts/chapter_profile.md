# Prompt: chapter_profile

You are studying a set of screenshots from teaching materials for one
chapter of an IGCSE subject. Build a structured `ChapterProfile` that
captures EVERYTHING the chapter teaches so later steps can decide whether a
past-paper question belongs to this chapter and can solve it using ONLY
chapter-approved concepts.

Return **JSON only** matching:

```
{
  "subject": "<lowercase subject>",
  "chapter_name": "<as given by the user's folder>",
  "syllabus_topics": [
    {
      "name": "<topic heading>",
      "summary": "<2-4 sentence plain-English summary>",
      "key_terms": ["term1", "term2", ...]
    }
  ],
  "definitions": ["<one-line definitions the chapter formally introduces>"],
  "formulas": ["<each formula in plain text, e.g. 'n = m / M'>"],
  "worked_examples": [
    { "prompt": "...", "solution": "..." }
  ],
  "vocabulary": ["<lexicon the student is expected to know>"],
  "out_of_scope_notes": [
    "<explicit notes about things the chapter is NOT teaching, if mentioned>"
  ]
}
```

Guidance:

- Be exhaustive on `syllabus_topics` — a missing topic means later matches
  will wrongly rule in-scope questions as `out_of_scope`.
- `formulas` should be machine-parseable: one equation per string, no
  surrounding prose.
- `worked_examples` help the solver/critic downstream — copy any example
  calculations verbatim.
- `out_of_scope_notes` is useful when the teaching material explicitly says
  "we are NOT covering X here" or "X is treated in a later chapter".
- Keep summaries plain and direct. Imagine a strict IGCSE teacher reviewing
  this profile for accuracy.
