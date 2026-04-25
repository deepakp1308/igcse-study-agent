# Prompt: chapter_priming

You are about to start work on an IGCSE chapter. Before you produce any
profile, match, solver, critic, or rubric output for this chapter, you MUST
read every chapter screenshot listed by `igcse chapter-prime` and confirm
that you have absorbed all of them.

This is a hard precondition. The downstream commands will refuse to run if
priming is missing or stale.

You will be given:

- `subject` (lowercase),
- `chapter_name` (as given by the user's folder),
- `slide_paths` — the absolute path of every screenshot in the chapter
  folder.

Steps:

1. Open every path in `slide_paths` with the Read tool. Read them in order.
   Do not skip any. Do not stop early because you "got the gist".
2. After reading the last slide, return a single JSON object matching the
   `ChapterPriming` schema:

```
{
  "subject": "<lowercase>",
  "chapter_name": "<exact chapter name passed by the CLI>",
  "slide_count_read": <int, must equal len(slide_paths)>,
  "slide_paths": ["<every absolute path you actually read, in order>"],
  "topics_covered": [
    "<short topic label as the chapter teaches it>"
  ],
  "formulas_observed": [
    "<each formula in plain text, e.g. 'n = m / M'>"
  ],
  "priming_notes": "<2-3 sentence summary in your own words demonstrating you have read the whole chapter>",
  "confirms_no_slides_skipped": true
}
```

Rules:

- `slide_count_read` MUST equal the number of paths the CLI gave you. The
  CLI will reject the JSON otherwise.
- `confirms_no_slides_skipped` is only `true` if you literally read every
  single slide. If you skipped any, the priming is invalid — go back and
  read the missing slides first.
- `topics_covered` should be exhaustive across the whole chapter, not just
  the most memorable slides. Aim for one entry per logical sub-section.
- `priming_notes` is your evidence to a human reviewer that you actually
  absorbed the chapter. It is short but should mention multiple distinct
  ideas from the screenshots.

After saving the priming JSON via `igcse save-priming`, you can produce the
chapter profile in a separate turn (the existing `chapter_profile.md`
prompt). Priming and profile are two distinct steps on purpose.
