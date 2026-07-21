"""HashingEmbedder tests — no database, no network, runs everywhere.

The hashing embedder is what makes the pgvector path CI-verifiable, so its
own properties need pinning: determinism across calls (and processes — it
hashes with md5, not the salted builtin), unit norm, and cosine behavior
that tracks the lexical similarity it approximates.
"""
import math

from correlation_engine.embeddings import HashingEmbedder


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # inputs are unit-norm


def test_deterministic_and_normalized():
    embedder = HashingEmbedder()
    first, second = embedder.embed(["connection pool exhausted"] * 2)
    assert first == second
    assert math.isclose(sum(v * v for v in first), 1.0, rel_tol=1e-9)


def test_cosine_tracks_lexical_similarity():
    embedder = HashingEmbedder()
    pool_a, pool_b, dns = embedder.embed([
        "connection pool exhausted after connectionPoolSize change",
        "DB connection pool exhausted",
        "coredns upstream resolver list rewritten",
    ])
    assert _cosine(pool_a, pool_b) > 0.5          # shared failure vocabulary
    assert _cosine(pool_a, dns) < 0.2             # disjoint vocabulary
    assert _cosine(pool_a, pool_b) > _cosine(pool_a, dns)


def test_empty_text_yields_zero_vector():
    (vector,) = HashingEmbedder().embed([""])
    assert not any(vector)  # callers guard on this before querying pgvector
