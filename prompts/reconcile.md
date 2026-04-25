# Prompt: reconcile

The solver and critic disagree on a question. You now have:

- `question_id`, `chapter_id`.
- The question stem and sub-parts.
- The chapter profile JSON.
- Both the solver's full `SolverOutput` JSON and the critic's
  `CriticOutput` JSON.

Your job is to produce a **final reconciled `SolverOutput`** that:

- Addresses the critic's specific `issues` point-by-point.
- Fixes any arithmetic or formula errors.
- Keeps `out_of_scope: false` only if every step still maps to the chapter
  profile. Otherwise set it to true and list what's missing.

Return **JSON only** matching `SolverOutput` (same schema as the solver).

Rules:

- If after reconciling you still don't have a chapter-supported answer,
  set `out_of_scope: true` and list missing concepts — honest "I can't
  teach this from the chapter alone" beats a wrong answer.
- Save this result with `igcse save-solution -`; this resets the critic
  slot. Then run a **fresh** critic turn (no memory of this reconciliation)
  using `prompts/critic.md`.
