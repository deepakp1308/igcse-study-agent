"""Evaluation harness for the IGCSE study agent.

Three datasets under this directory:

* ``chapter_match.yaml`` - (question_stem, chapter_name, should_match) tuples
  used for offline precision/recall estimates.
* ``solution_quality.yaml`` - (question_stem, gold_solution, gold_chapter_refs)
  used with an LLM-as-judge scorer in CI.
* ``rubric_grader.yaml`` - (rubric_json, student_answer, gold_marks, tolerance)
  used to verify the simulator's static grader agrees with human marks.

Only ``rubric_grader`` can run fully offline. The other two produce metrics
when the agent is actively driving the pipeline; in CI we still schema-check
the YAML files and exercise the match/solution code paths on fake fixtures.
"""
