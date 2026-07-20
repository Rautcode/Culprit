"""Thin model abstraction — the one framework-shaped piece that earns its
keep (docs/07-ai-architecture.md "Model selection"): provider/model swaps are
a config change, and the harness runs a deterministic scripted stub instead
of a network call. No LangChain-style framework — the protocol is one method.
"""
from __future__ import annotations

from typing import Protocol


class ModelClient(Protocol):
    def complete(self, system: str, prompt: str) -> str:
        """One completion. Returns the raw text; the explainer parses it."""
        ...


class ScriptedModel:
    """Deterministic stand-in for tests and the harness: returns a canned
    response and records every call for inspection. This is what keeps the
    LLM layer's contract (prompt shape, output schema, guardrails) fully
    testable in CI with zero network access."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


class AnthropicModel:
    """Production client. Not exercised in CI (no key, no network) — the
    contract it must satisfy is pinned by the ScriptedModel test suite.
    Adaptive thinking per current API guidance; no sampling params.
    """

    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 4096) -> None:
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            return ""
        return "".join(block.text for block in response.content if block.type == "text")
