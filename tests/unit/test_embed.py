"""Local embedding helpers under fake mode."""

from __future__ import annotations

import numpy as np

from agent.embed.local import cosine, cosine_matrix, embed_texts


def test_fake_embed_shape_and_determinism(fake_embed_env):
    a = embed_texts(["hello world"])
    b = embed_texts(["hello world"])
    assert a.shape == (1, 64)
    assert np.allclose(a, b)


def test_fake_embed_distinct_for_distinct_texts(fake_embed_env):
    a = embed_texts(["alpha"])[0]
    b = embed_texts(["beta"])[0]
    assert cosine(a, b) < 0.99  # not identical


def test_cosine_identity_is_one(fake_embed_env):
    a = embed_texts(["hello"])[0]
    assert cosine(a, a) == 1.0 or abs(cosine(a, a) - 1.0) < 1e-5


def test_cosine_matrix_shape(fake_embed_env):
    a = embed_texts(["a", "b"])
    b = embed_texts(["a", "b", "c"])
    m = cosine_matrix(a, b)
    assert m.shape == (2, 3)
    # diagonal should be ~1 for matching indices
    assert abs(m[0, 0] - 1.0) < 1e-5
    assert abs(m[1, 1] - 1.0) < 1e-5
