# Prompt: extract_questions

You are looking at one page of an IGCSE past paper. Extract every question or
question-part visible on this page as structured JSON.

Return **JSON only** matching `PageExtraction`:

```
{
  "paper_id": <will be filled by CLI, you can set 0>,
  "page_idx": <will be filled by CLI, you can set 0>,
  "questions": [
    {
      "number": "<e.g. '1', '7', 'B3'>",
      "type": "mcq" | "short" | "long" | "structured" | "numeric",
      "marks": <int>,
      "stem": "<the leading question text before any sub-parts>",
      "sub_parts": [
        { "label": "a", "prompt": "...", "marks": <int>, "type": "short" | "long" | "numeric" }
      ],
      "options": null | [
        { "label": "A", "text": "..." },
        { "label": "B", "text": "..." },
        ...
      ],
      "figure_bboxes": [ { "x": 0..1, "y": 0..1, "w": 0..1, "h": 0..1 } ],
      "confidence": <float 0..1>,
      "notes": "<optional freeform note e.g. 'figure is a circuit diagram'>"
    }
  ]
}
```

Rules:

- One entry per **question number** on the page. Sub-parts (a, b, c, i, ii)
  belong in `sub_parts`, not as separate top-level entries.
- If a question **starts** on this page and continues to the next, include
  what's visible with a `notes` hint `"continues"`. If a question **ends**
  on this page having started earlier, prefix `notes` with `"begins previous page"`.
- MCQ: put options in `options`, leave `sub_parts` empty.
- Structured questions with multiple parts: leave `options` null.
- Figure bboxes use normalized (0..1) coords relative to the page image,
  origin top-left. Pad ~2% around each figure.
- Strip footers like "[Turn over]", "© UCLES", "[Total: N]" from the stem.
- `marks` is the top-line mark total for the question (sum of sub-part marks
  if listed). 0 is fine for pure stems that only host sub-parts.
- `confidence`: be honest. Hard-to-read handwriting-style chemistry or a
  partially cropped page should drop confidence below 0.75, which routes the
  question to human review.

If no questions are visible (cover page, instructions page, blank), return:

```
{ "paper_id": 0, "page_idx": 0, "questions": [] }
```
