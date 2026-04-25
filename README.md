# IGCSE study agent (zero-key edition)

A practice-paper, worked-solutions, and exam-simulator generator for IGCSE past
papers, driven entirely by the Cursor agent — no API keys to manage.

For a given chapter (e.g. _Chemistry / The Mole_), the agent produces:

1. **Practice paper PDF** — every past-paper question that belongs to the
   chapter, with answer spaces sized proportionally to marks.
2. **Worked solutions PDF** — chapter-aligned derivations with
   "From your chapter:" citations; questions that stretch past the chapter get
   a "review with teacher" banner instead of a fabricated answer.
3. **Static exam simulator** on GitHub Pages — MCQ / numeric / short-text /
   free-text grading with precomputed rubrics; concept-level feedback, common
   mistake detection, and a per-topic score breakdown. **Works with zero
   API keys and zero tracking** — the static grader runs entirely in the
   student's browser.

## How it splits work

- **Main agent** (Cursor session): reads past-paper PNGs and chapter
  screenshots, extracts questions, builds chapter profiles, judges matches,
  writes solutions, and produces grading rubrics.
- **Independent critic** (in-session turn): re-derives every solution from
  scratch and disagrees if the main agent's working has errors.
- **Extraction auditor** (Cursor `Task` subagent, `explore` type, readonly):
  runs after every per-page extraction. Independently re-reads the page PNG
  and verifies no questions or sub-parts were missed. Up to 2 iterations.
- **Solution judge** (in-session turn): scores every solver+critic answer on
  five dimensions (correctness, clarity, age-appropriateness for a
  15-year-old, IGCSE mark-scheme alignment, completeness). Drives an
  improve-loop until `quality_score >= 0.85`. Max 2 improve cycles.
- **Python CLI** (deterministic work): renders PDFs to page PNGs, crops
  figures, stores everything in SQLite, runs local embeddings for
  dedup/recall, lays out the practice-paper and solutions PDFs, bakes the
  simulator's rubric JSON + copies the latest PDFs into the public folder,
  builds the Vite React frontend.
- **Static simulator** (browser): loads the rubric JSON, grades MCQ exactly,
  grades numeric with tolerance, grades free-text by concept coverage
  (optional in-browser MiniLM embeddings via
  [`@xenova/transformers`](https://github.com/xenova/transformers.js)), and
  always shows the model answer + chapter references. Practice paper and
  worked solutions PDFs are downloadable directly from the landing page.

Hard preconditions:

1. **No matching, no solving, no rubric, no PDF, no simulator build for any
   chapter that has not been primed.** `igcse chapter-prime` requires the
   agent to read EVERY slide before downstream work runs.
2. **No PDF or simulator deploy if any included solution has
   `final_quality_score < 0.75`** after the judge loop.

See `[AGENT_SOP.md](AGENT_SOP.md)` for the full step-by-step runbook
(Steps 0 priming, 1 ingest, 1c audit, 2 chapter profile, 3 match,
4 solver+critic, 4c judge+improve, 5 paper PDF, 6 solutions PDF,
7 simulator build) and `[prompts/](prompts/)` for the prompt templates.

## Quickstart (macOS)

### 1. Install the Python pipeline

```bash
cd igcse-study-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

### 2. Install the simulator build tools

```bash
cd simulator
npm install
cd ..
```

### 3. Organize your inputs

The agent expects two folders anywhere on your Mac. Their layouts:

```
<papers folder>/
  chemistry/
    0620_12_2018.pdf
    0620_42_2019.pdf
    ...
  physics/
    ...

<chapter materials folder>/
  chemistry/
    The Mole/
      01-slide1.png
      02-slide2.png
      ...
    Electrolysis/
      ...
  physics/
    ...
```

Subject subfolder names are free-form (`chemistry`, `physics`, `Mathematics`,
`french`, ...). Chapter subfolder names are whatever you use; you'll pass the
same name back later.

### 4. Render papers (Python) then extract (agent)

In a Cursor chat, tell the agent (or run yourself):

```bash
igcse ingest-papers --papers-dir /path/to/papers
```

The CLI renders every page to `pages_cache/paper-<id>/page-<NNNN>.png` and
prints **agent instructions**. The agent (me) then runs one turn per page:
reads the PNG, produces `PageExtraction` JSON, and pipes it into
`igcse save-questions ... -`. Low-confidence extractions land in
`igcse review`.

### 5. Build chapter profiles

```bash
igcse ingest-chapters --chapters-dir /path/to/chapters
```

Same pattern: the agent reads each chapter's screenshots in order, produces
`ChapterProfile` JSON, and saves it via `igcse save-chapter`.

### 6. Pick a chapter, match, generate

```bash
igcse match --subject chemistry --chapter "The Mole"
# Agent produces MatchDecision for each candidate → save-match

igcse generate-paper --subject chemistry --chapter "The Mole"
# → output/practice_paper_chemistry_the-mole_<timestamp>.pdf

igcse generate-solutions --subject chemistry --chapter "The Mole"
# Agent writes solver JSON + critic JSON for each matched question.
# → output/solutions_chemistry_the-mole_<timestamp>.pdf

igcse build-simulator --subject chemistry --chapter "The Mole"
# Agent writes a QuestionRubric per question → bakes sets/<subject>-<chapter>.json.
# Then runs `npm run build` in simulator/.
```

### 7. Deploy

Push the repo to GitHub, enable Pages on the repo settings (source: GitHub
Actions). The `.github/workflows/deploy-pages.yml` workflow builds and
publishes the simulator. Your daughter's URL:

```
https://<your-github-user>.github.io/igcse-study-agent/?set=<subject>-<chapter>
```

## Quality gates

- **Schema-guarded**: every agent JSON output is pydantic-validated; failures
  go to `review_queue` and block writes to SQLite.
- **Confidence thresholds**: extractions with `confidence < 0.75` are flagged
  for quick human review via `igcse review`.
- **Precision-tuned matcher**: default `0.78` similarity threshold. It is far
  better to miss a tangentially related question than include an off-chapter
  one.
- **Independent critic**: every solution gets re-graded by a fresh critic
  turn. Critic-disagreement rate > 15% blocks the PDF build until reviewed.
- **Out-of-scope banner**: the solver refuses to fabricate answers for
  questions the chapter profile doesn't cover.
- **Rubric grader agreement eval**: `evals/rubric_grader.yaml` holds
  hand-graded cases; CI blocks deploy if the static grader's agreement with
  human marks drops below 85%.

## Testing

```bash
# Python
pytest -q                # unit + integration
python -m evals.run      # rubric grader eval
ruff check agent tests
mypy agent

# Simulator
cd simulator
npm run test
npm run build
```

## Privacy

Your daughter's past papers and chapter screenshots never leave your Mac.
Only the simulator's static bundle (sanitized questions + rubrics + model
answers) is published to GitHub Pages. The simulator itself calls no third-
party API at runtime — the MiniLM model for optional embedding similarity is
downloaded from the Hugging Face CDN into your browser cache the first time
the student uses free-text grading, and all evaluation happens client-side.

## Repo layout

- `[agent/](agent/)` — Python deterministic toolkit (CLI, PDF render, SQLite,
  embeddings, PDF generators, site data baker).
- `[AGENT_SOP.md](AGENT_SOP.md)` — runbook the Cursor agent follows.
- `[prompts/](prompts/)` — prompt templates the agent pastes into its own
  context.
- `[simulator/](simulator/)` — Vite+React static exam simulator.
- `[evals/](evals/)` — labeled golden sets + harness.
- `[.github/workflows/](.github/workflows/)` — CI and Pages deploy.

## Credits

Built during a Cursor session on April 25, 2026. Licensed MIT. Made with care
for a 10-year-old who deserves better practice than random PDFs dumped on her
desk.
