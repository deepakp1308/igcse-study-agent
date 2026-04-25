"""Shared fixtures: isolated DB + caches per test, fake embeddings."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agent.store.db import init_db


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "igcse.sqlite"
    pages = tmp_path / "pages_cache"
    figs = tmp_path / "figures_cache"
    out = tmp_path / "output"
    monkeypatch.setenv("IGCSE_DB_PATH", str(db))
    monkeypatch.setenv("IGCSE_PAGES_DIR", str(pages))
    monkeypatch.setenv("IGCSE_FIGURES_DIR", str(figs))
    monkeypatch.setenv("IGCSE_OUTPUT_DIR", str(out))
    monkeypatch.setenv("IGCSE_FAKE_EMBED", "1")
    for d in (pages, figs, out):
        d.mkdir(exist_ok=True, parents=True)
    init_db(db)


@pytest.fixture()
def fake_embed_env() -> None:
    os.environ["IGCSE_FAKE_EMBED"] = "1"
