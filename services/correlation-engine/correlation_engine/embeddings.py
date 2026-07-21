"""Embedders behind the incident-memory interface (memory.py's named trigger).

The Embedder protocol is one method; two implementations:

  HashingEmbedder — deterministic feature hashing of the SAME token stream
  the lexical memory uses (_vectorize's tokenizer + stopwords), L2-normalized
  into fixed-dim vectors. A real embedding function (the hashing trick), not
  a mock: it makes pgvector retrieval fully testable in CI with no network,
  and its cosine approximates the lexical cosine (hash collisions aside).

  VoyageEmbedder — the production, semantic embedder. Anthropic offers no
  embeddings endpoint; Voyage AI is the recommended partner. Implemented
  over stdlib urllib (no new dependency), key-gated and NOT exercised in
  CI — the same contract-pinned pattern as ai_reasoning.model.AnthropicModel.
  Verify the model name against Voyage's docs when wiring a real key.

Scoring default is unchanged: the lexical IncidentMemory remains the
default backend. Switching to embeddings is gated on the eval comparison
the original trigger named — run the golden set through both and let
precision decide, not novelty.

One embedder per store: vectors from different embedders (different dims,
different spaces) must never share columns — re-embed everything when
switching (see PgVectorIncidentMemory).
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.request
from typing import Protocol

from .memory import _vectorize


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """One vector per input text, all the same dimension."""
        ...


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self.dim
            for token, count in _vectorize(text).items():
                # Stable across processes (hash() is salted; md5 is not).
                bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
                vector[bucket] += count
            norm = math.sqrt(sum(v * v for v in vector))
            if norm:
                vector = [v / norm for v in vector]
            vectors.append(vector)
        return vectors


class VoyageEmbedder:
    """Production semantic embeddings via Voyage AI. Not exercised in CI
    (needs VOYAGE_API_KEY); the pgvector plumbing it feeds is proven with
    HashingEmbedder instead."""

    def __init__(self, api_key: str, model: str = "voyage-3-lite") -> None:
        self._api_key = api_key
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        request = urllib.request.Request(
            "https://api.voyageai.com/v1/embeddings",
            data=json.dumps({"input": texts, "model": self._model}).encode(),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        payload = self._post_with_retry(request)
        # Sort by the API's `index` rather than trusting array order — the
        # eval comparison relies on embeddings lining up with their inputs,
        # and a reordered response would silently mismatch symptom/cause vecs.
        items = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in items]

    @staticmethod
    def _post_with_retry(request, attempts: int = 3):
        # A 300-call eval comparison shouldn't abort on one transient blip.
        # Retry 429/5xx and connection errors with exponential backoff; 4xx
        # (bad key, bad request) fails fast — retrying won't help.
        import time

        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                    raise
            except urllib.error.URLError:
                if attempt == attempts - 1:
                    raise
            time.sleep(2 ** attempt)
