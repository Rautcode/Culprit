# Contributing to Culprit

Thanks for looking. Culprit is deliberately small and disciplined — this
guide gets you productive fast and explains the one workflow rule that
makes the project what it is.

## The 30-second orientation

- **What to read first:** [README.md](README.md) → [CASE-STUDY.md](CASE-STUDY.md)
  (why it's built this way) → [SPEC_VERSION.md](SPEC_VERSION.md) (the frozen
  decisions) → [docs/](docs/) (the design set).
- **The core idea you must not break:** the correlation is *deterministic*.
  A Rule Engine + Knowledge Graph produce the verdict with cited evidence;
  the LLM only explains, bounded so it cannot invent. Contributions that
  move causal reasoning into the LLM will be declined — see
  [docs/07-ai-architecture.md](docs/07-ai-architecture.md).

## Set up (2 minutes, no credentials)

```
python -m pytest services/correlation-engine/tests services/ai-reasoning/tests -v
python -m correlation_engine.cli demo deadlock     # from services/correlation-engine
```

If those pass and the demo prints a verdict, you're set. The Postgres/
pgvector tests skip locally without a database and run in CI; to run them
locally, `docker-compose up -d postgres` and set `POSTGRES_DSN`.

The web UI: `cd apps/web && npm install && npm run dev`.

## The one rule: the spec is frozen, changes go through an ADR

Frozen decisions live in [SPEC_VERSION.md](SPEC_VERSION.md) — the rule set,
the confidence formula, the ±15% LLM bound, the graph edge types. Changing
any of them requires an [ADR](docs/adr/) and an amendment-log entry, not a
silent edit. This is the discipline that keeps the project coherent; PRs
that quietly change a frozen item will be asked to add the ADR first.

Everything *not* frozen — new scenarios, rule *weight* tuning, UI, docs,
robustness, performance — is fair game without ceremony.

## The best first contribution: add a harness scenario

The [incident simulation harness](services/correlation-engine/correlation_engine/harness/scenarios/)
is where the engine's correctness lives, and it's the most valuable and
approachable place to contribute. A good scenario is a real incident shape
the catalog doesn't cover yet, with a clear culprit and at least one decoy.

1. Copy an existing scenario file (e.g. `deadlock.py`) and adapt it.
2. Register its `build()` in `scenarios/__init__.py`.
3. `python -m pytest` — the parametrized suite verifies it end to end.
4. If your scenario needs an engine change to pass, that's the interesting
   case — the harness caught three real graph-direction bugs this way. Fix
   the engine, and your scenario becomes the regression guard.

## PR expectations

- **Tests pass, CI green.** Non-trivial logic gets a test; the golden-set
  precision gate (precision@1 = 100%) must hold — a ranking change that
  flips it fails before merge.
- **Match the surrounding style.** Comment density, naming, the honest
  "proven vs. designed" framing. If you defer something, mark it with a
  `# ponytail:` comment naming the ceiling and the upgrade path.
- **Small, focused diffs.** One concern per PR.
- **Be honest in docs.** This repo never claims a capability it doesn't
  have. Keep it that way.

## Good places to start

- Add a harness scenario (above) — the highest-value entry point.
- Improve `culprit diagnose` input handling or error messages.
- Web UI: the deferred light theme / shadcn/ui pass in
  [docs/08-ui-design.md](docs/08-ui-design.md).
- Docs: fix anything unclear; the design set is large.
- Tests: edge cases in the adapters or the confidence math.

Issues labeled `good first issue` and `help wanted` are curated for newcomers.

## Reporting bugs & security

Open an issue for bugs. For security, see [SECURITY.md](SECURITY.md) — do
not open a public issue for a vulnerability.

## Conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
