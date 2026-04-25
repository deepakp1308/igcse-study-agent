"""IGCSE past-paper study agent (zero-key edition).

The Python package holds deterministic helpers only (PDF rendering, SQLite I/O,
PDF layout, static-site build, CLI orchestration). All LLM-driven steps
(extraction, matching, solving, rubric writing) are performed by the Cursor
agent following ``AGENT_SOP.md`` and the prompts under ``prompts/``.
"""

from agent.version import __version__

__all__ = ["__version__"]
