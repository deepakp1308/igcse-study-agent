# Practice releases

PDFs and simulator URL for the current practice batch.

## Combined Science / Electrochemistry — first batch (Apr 2026)

- Practice paper: [`Electrochemistry_Practice_Paper.pdf`](Electrochemistry_Practice_Paper.pdf)
- Worked solutions: [`Electrochemistry_Worked_Solutions.pdf`](Electrochemistry_Worked_Solutions.pdf)
- Live simulator: <https://deepakp1308.github.io/igcse-study-agent/?set=combined-science-electrochemistry.json>

3 questions matched against the chapter:

| # | Source | Type | Topic |
|---|---|---|---|
| 1 | 0653 / Paper 22 / Q19 | MCQ | Electrical conductivity of solutions (electrolyte concept) |
| 2 | 0653 / Paper 22 / Q23 | MCQ | Iron extraction (electrolysis vs blast-furnace reduction) |
| 3 | 0653 / Paper 22 / Q27 | MCQ | Products of electrolysis: molten / aqueous / sulfuric acid |

## How to add more questions to this set

1. Drop more `*.pdf` files into your local `papers_working/<subject>/` folder.
2. Run `igcse ingest-papers --papers-dir papers_working` to render new pages.
3. Drive the agent through `extract_questions` for each new page (see `AGENT_SOP.md`).
4. Re-run `igcse match`, `igcse generate-paper`, `igcse generate-solutions`, `igcse build-simulator` and push.
5. The Pages workflow will redeploy automatically.
