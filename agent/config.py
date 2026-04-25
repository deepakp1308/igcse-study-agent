"""Configuration constants and path resolution.

Keep this tiny and centralized so tests can override via env vars.
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def db_path() -> Path:
    override = os.environ.get("IGCSE_DB_PATH")
    if override:
        return Path(override)
    return repo_root() / "agent" / "db.sqlite"


def pages_cache_dir() -> Path:
    override = os.environ.get("IGCSE_PAGES_DIR")
    if override:
        return Path(override)
    return repo_root() / "pages_cache"


def figures_cache_dir() -> Path:
    override = os.environ.get("IGCSE_FIGURES_DIR")
    if override:
        return Path(override)
    return repo_root() / "figures_cache"


def output_dir() -> Path:
    override = os.environ.get("IGCSE_OUTPUT_DIR")
    if override:
        return Path(override)
    return repo_root() / "output"


def simulator_sets_dir() -> Path:
    return repo_root() / "simulator" / "public" / "sets"


def simulator_dist_dir() -> Path:
    return repo_root() / "simulator" / "dist"


RENDER_DPI = 200
MATCH_THRESHOLD_DEFAULT = 0.78
DEDUP_COSINE_DEFAULT = 0.92
LOW_CONFIDENCE_THRESHOLD = 0.75
CRITIC_DISAGREEMENT_BLOCK_RATE = 0.15

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
