# Prompt: rubric

You are writing a grading rubric for one IGCSE question that will be used
by a static (no-LLM) browser grader. The rubric is the entire source of
truth for the simulator's feedback, so be thorough.

You will be given:

- The question (stem, sub-parts, figure paths) from `igcse show-question`.
- The reconciled `SolverOutput` (the chapter-aligned model answer).
- The chapter profile JSON.

Return **JSON only** matching `QuestionRubric`:

```
{
  "question_id": "<stable string id, e.g. '2018-chem-p2-q3'>",
  "source_question_db_id": <int, the DB id from show-question>,
  "type": "mcq" | "short" | "long" | "structured" | "numeric",
  "max_marks": <int>,
  "stem": "<question stem, cleaned>",
  "figure_paths": ["<paths as given in show-question>"],
  "parts": [
    {
      "id": "<'a', 'b', 'i', ...>",
      "prompt": "<sub-part prompt, or the full stem if no sub-parts>",
      "answer_type": "mcq" | "numeric" | "short_text" | "free_text" | "self_check",
      "max_marks": <int>,
      "mcq_options": null | [ {"label": "A", "text": "..."} ],
      "mcq_correct_label": null | "A",
      "numeric_answer": null | <float>,
      "numeric_unit": null | "mol",
      "numeric_tolerance_pct": null | <float 0..100>,
      "accepted_phrasings": ["<wordings that should count as correct for short_text>"],
      "required_working_concepts": [
        {
          "concept": "<plain English description of a mark-bearing concept>",
          "marks": <int>,
          "hints": ["<short phrases likely to appear if the student shows it>"]
        }
      ],
      "common_mistakes": [
        {
          "match": {
            "kind": "formula_inverted" | "keyword_absent" | "keyword_present" | "numeric_off_by",
            "keyword": "<only for keyword_* kinds>",
            "magnitude": <only for numeric_off_by: float, e.g. 10 for off by x10>
          },
          "feedback": "<specific, kind explanation of what went wrong and how to fix it>"
        }
      ],
      "model_answer_html": "<HTML-safe model answer with equations in <b>...</b>>",
      "chapter_refs": ["<chapter topics/formulas/definitions this part relies on>"]
    }
  ]
}
```

Rules:

- **MCQ**: fill `mcq_options`, `mcq_correct_label`, leave numeric fields
  null. `required_working_concepts` can stay empty; the browser grader
  only checks exact-match.
- **Numeric**: fill `numeric_answer`, `numeric_unit`, and a realistic
  `numeric_tolerance_pct` (2-5% is common for IGCSE). Also fill
  `required_working_concepts` for the method (formula, correct substitution,
  units) so partial credit is possible.
- **short_text** (e.g. "name the process" / "state the definition"):
  populate `accepted_phrasings` with at least 3 equivalent correct wordings.
- **free_text** (explain/describe): rely on `required_working_concepts` with
  plenty of `hints` so the in-browser embedding grader can detect concept
  coverage. 3-6 concepts is typical.
- **self_check** (composition / essay / translation): set the answer type
  to `self_check`, leave numeric and options null, still fill
  `required_working_concepts` as a checklist, and put the model answer in
  `model_answer_html`. The simulator will let the student tick off
  concepts rather than auto-grade.
- `common_mistakes` is where you spend the most care. Put the 2-4 most
  likely wrong patterns for IGCSE students and write tailored feedback for
  each. This is what turns the simulator from a grader into a teacher.
- `chapter_refs` must reuse exact strings from the chapter profile so the
  student sees "From your chapter: <topic>".
- `model_answer_html` must be valid HTML fragment (no `<html>` or `<body>`
  tags). Use `<b>`, `<i>`, `<br/>`, `<sup>`, `<sub>`, `<code>` as needed.
