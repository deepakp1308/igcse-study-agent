"""Local embeddings via sentence-transformers MiniLM.

We load the model lazily so importing the package is cheap (important for
CLI startup). Falls back to a deterministic hash-based pseudo-embedding when
``IGCSE_FAKE_EMBED=1`` is set - this is what unit tests and CI use so they
don't need to download model weights.
"""

from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import NDArray

from agent.config import EMBED_MODEL

FAKE_DIM = 64


def _fake_embed(text: str) -> NDArray[np.float32]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    rng = np.random.default_rng(int.from_bytes(h[:8], "big"))
    v = rng.normal(size=FAKE_DIM).astype(np.float32)
    n = np.linalg.norm(v)
    if n > 0:
        v = v / n
    return v


@lru_cache(maxsize=1)
def _model() -> Any:
    """Return the MiniLM SentenceTransformer, loading it on first call."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBED_MODEL)


def embed_texts(texts: list[str]) -> NDArray[np.float32]:
    if os.environ.get("IGCSE_FAKE_EMBED") == "1":
        return np.stack([_fake_embed(t) for t in texts]).astype(np.float32)
    vecs = _model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    arr: NDArray[np.float32] = np.asarray(vecs, dtype=np.float32)
    return arr


def cosine(a: NDArray[np.float32], b: NDArray[np.float32]) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cosine_matrix(a: NDArray[np.float32], b: NDArray[np.float32]) -> NDArray[np.float32]:
    """Pairwise cosine similarity matrix (a.shape[0] x b.shape[0])."""

    na = np.linalg.norm(a, axis=1, keepdims=True)
    nb = np.linalg.norm(b, axis=1, keepdims=True)
    na = np.where(na == 0.0, 1.0, na)
    nb = np.where(nb == 0.0, 1.0, nb)
    a_n = a / na
    b_n = b / nb
    result: NDArray[np.float32] = (a_n @ b_n.T).astype(np.float32)
    return result
