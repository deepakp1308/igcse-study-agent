# AGENT_SOP.md

This is the runbook the Cursor agent follows to produce all LLM outputs for
the IGCSE study agent. Every LLM step has:

1. an **input surface** (image files, DB rows, prompt template),
2. a **pydantic schema** the response must validate against, and
3. a **save CLI** that persists the validated response.

No LLM secrets are ever referenced; the agent is the LLM.

When a save CLI rejects a payload with schema errors, it parks the raw
response in `review_queue` automatically and exits non-zero. Retry once
with the validation error appended to the prompt; on a second failure,
move on and ask the user to open `igcse review`.

---

## Conventions

- Use absolute JSON: no trailing commas, no comments. Use double quotes. When
  uncertain about a field, omit it rather than guess.
- Every numeric `marks` field is an integer. Round 0.5 marks up.
- Normalize stems to Unicode text; strip page-number artifacts like
  "Turn over" or "[Total 12]".
- For figure bounding boxes, use normalized coords (0..1) on the rendered
  page PNG, origin top-left. Include a little padding (~2%) around each
  figure so cropped PNGs aren't clipped.
- Every extraction includes a `confidence` in `[0.0, 1.0]`. If you'd stake
  coffee on it, use `>=0.85`. If you'd only bet a low-stakes guess, use
  `0.5`. Anything `<0.75` routes the question to `igcse review` for a
  human sanity check.

---

## Step 1 — Ingest past papers

Driver: `igcse ingest-papers --papers-dir <PATH>`

The CLI walks the folder, renders pages to PNGs, and prints instructions
per paper. For each paper you then run:

### 1a. Paper metadata (once per paper)

- **Input**: `pages_cache/paper-<id>/page-0000.png` (the cover page). If the
  cover page is empty/sparse, also read page 1.
- **Prompt**: `prompts/extract_paper_metadata.md`
- **Schema**: `PaperMetadata` (`agent/store/schemas.py`)
- **Save**:

  ```sh
  igcse save-paper-metadata --paper-id <ID> - <<'JSON'
  { ... PaperMetadata JSON ... }
  JSON
  ```

### 1b. Per-page question extraction

For each page PNG `pages_cache/paper-<id>/page-<NNNN>.png`:

- **Input**: the page PNG (Read tool).
- **Prompt**: `prompts/extract_questions.md`
- **Schema**: `PageExtraction` (list of `ExtractedQuestion`)
- **Save**:

  ```sh
  igcse save-questions --paper-id <ID> --page-idx <N> - <<'JSON'
  { ... PageExtraction JSON ... }
  JSON
  ```

Notes:

- Keep sub-parts of a single question together under `sub_parts` rather
  than creating separate top-level entries.
- Figure bboxes are cropped to disk by the CLI; you do **not** need to
  describe the figures in the stem. The student sees the original crop.
- MCQ options go in `options`, not in `stem`.

---

## Step 2 — Build chapter profiles

Driver: `igcse ingest-chapters --chapters-dir <PATH>`

For each chapter listed in the output:

- **Input**: all `*.png` screenshots in `Subject/Chapter/` in filename order.
- **Prompt**: `prompts/chapter_profile.md`
- **Schema**: `ChapterProfile`
- **Save**:

  ```sh
  igcse save-chapter --subject <S> --name <C> \
    --screenshots-dir <PATH> - <<'JSON'
  { ... ChapterProfile JSON ... }
  JSON
  ```

---

## Step 3 — Match questions to a chapter

Driver: `igcse match --subject <S> --chapter <C>`

The CLI prints a ranked candidate shortlist (deterministic embeddings) plus
the chapter profile. For **each candidate** row:

- **Input**: the question stem (shown in CLI output) + the chapter profile
  JSON (printed below the table).
- **Prompt**: `prompts/match_verify.md`
- **Schema**: `MatchDecision`
- **Save**:

  ```sh
  igcse save-match - <<'JSON'
  { ... MatchDecision JSON ... }
  JSON
  ```

Guardrails:

- Default to `fit = "none"` unless the chapter profile covers the concept
  being tested. Precision > recall.
- `fit = "partial"` only when most of the question is in-scope but a small
  step needs an external concept. Flag that step in `missing_concepts`.
- Always fill `rationale` in one or two sentences.

---

## Step 4 — Produce solutions (solver + critic)

Driver: `igcse generate-solutions --subject <S> --chapter <C>`

On the first run, the CLI lists pending question ids and exits. For each
pending `question_id`:

### 4a. Solver (one turn)

- **Input**: `igcse show-question <qid>` (prints stem/sub-parts/figures) and
  the chapter profile JSON.
- **Prompt**: `prompts/solver.md`
- **Schema**: `SolverOutput`
- **Save**: `igcse save-solution -`

Write the answer using ONLY concepts from the chapter profile. If the
question requires concepts not listed in the profile, set `out_of_scope: true`
and list the missing concepts; do NOT fabricate a derivation.

### 4b. Critic (separate turn — important!)

Start a **fresh** turn (no memory of the solver's reasoning) and open the
question text + chapter profile again.

- **Prompt**: `prompts/critic.md`
- **Schema**: `CriticOutput`
- **Save**: `igcse save-critic -`

When the critic disagrees with the solver, the CLI parks a
`critic_disagreement` row in `review_queue` and leaves `reconciled_json`
unset. Run one more turn using `prompts/reconcile.md`, again saving with
`save-solution` (which resets the critic slot) and then a fresh
`save-critic` turn. If disagreement persists, leave it for human review.

Re-run `generate-solutions` once all pending items are saved; it will
assemble the PDF.

---

## Step 5 — Build per-question rubrics (simulator fuel)

For each matched question that has a reconciled solution:

- **Input**: `igcse show-question <qid>`, the reconciled `SolverOutput` for
  the question (from the `solutions` table), and the chapter profile.
- **Prompt**: `prompts/rubric.md`
- **Schema**: `QuestionRubric`
- **Save**: `igcse save-rubric --chapter-id <CHID> -`

The rubric is the heart of the static simulator. Be generous with
`accepted_phrasings`, `required_working_concepts`, and `common_mistakes` —
those are the signals the in-browser grader uses.

For questions where the answer is numeric, always fill `numeric_answer`,
`numeric_unit`, and `numeric_tolerance_pct`. For MCQ, fill
`mcq_correct_label` and mirror `mcq_options` from the question.

For essay-style prompts (English / French), set `answer_type: "self_check"`;
the simulator will show the model answer + rubric and let the student tick
off what she hit rather than auto-scoring.

When all rubrics are saved:

```sh
igcse build-simulator --subject <S> --chapter <C>
```

---

## Step 6 — Deploy

Commit the repo and push to GitHub. The `.github/workflows/deploy-pages.yml`
workflow builds the simulator and publishes to `gh-pages`. Your daughter's
URL is `https://<your-github-user>.github.io/igcse-study-agent/?set=<subject>-<chapter>`.

---

## Emergency protocols

- **Schema failure**: CLI exits 2 and parks raw JSON in `review_queue`. Retry
  once with the error appended; if it still fails, stop and ask the user.
- **Critic disagreement rate > 15%**: `generate-solutions` exits 3. Don't
  rebuild the PDF. Open `igcse review` and walk through disagreements.
- **Low-confidence extractions (>10% of questions)**: `igcse review` lists
  them; compare the extracted JSON to the page PNG and correct in SQLite
  (by re-running `save-questions` for that page).
- **Out-of-scope question in match shortlist**: set `fit: "none"` with a
  rationale. It will not enter the paper or solutions.
