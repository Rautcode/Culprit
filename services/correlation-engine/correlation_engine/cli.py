"""culprit — the Phase 0 validation CLI (docs/02-product-decision.md).

Two commands, two audiences:

  demo      Run a harness incident through the real pipeline and print the
            verdict. Zero credentials, zero setup — the artifact you show
            in a first conversation. Uses leave-one-out incident memory so
            the numbers match the web UI's export.

  diagnose  Run the pipeline on a design partner's OWN evidence, supplied
            as files: `kubectl get events -o json` output plus a simple
            deploys JSON. File-based by design — the lowest-trust ask for
            a skeptical SRE: no agent install, no credentials handed over,
            works offline. Live collection (kubeconfig/GitHub API) is the
            Phase 1 Collector's job, not this CLI's. With --memory-dsn,
            verdicts include precedent from persistent incident memory
            (lexical by default; --memory-backend pgvector for SQL cosine
            retrieval via embeddings.py). With --explain, an LLM narrates
            the verdict on top of the deterministic evidence — bounded by
            the grounding guardrail; the verdict itself is unchanged.

  eval      Print the golden-set evaluation report (SPEC_VERSION.md
            v1.0 Evaluation Metrics): per-layer precision with the
            RAG-adds-no-noise gate, and per-rule precision feeding weight
            tuning. CI publishes this into every run's summary. With
            --memory-dsn, also compares the lexical vs pgvector memory
            backends on the golden set (isolated + rolled back) — the data
            behind the embeddings.py adoption gate.

  learn     Record a confirmed incident into persistent memory — the
            "Learn" step of the core loop, closing the feedback cycle so
            future diagnose runs cite it as precedent. Seed a demo store
            with --from-scenario all.

Run as `python -m correlation_engine.cli ...` from services/correlation-engine,
or `culprit ...` after `pip install -e services/correlation-engine`.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .harness.scenarios import ALL_SCENARIOS, get
from .harness.schema import AlertEvent, DeployEvent, EvidenceBundle, ServiceEdge
from .knowledge_graph import KnowledgeGraph
from .memory import IncidentMemory
from .pipeline import RCAResult, build_timeline, rank_candidates, run_scenario
from .collection.adapters import parse_k8s_event


def _ts(value: str) -> datetime:
    """ISO-8601 -> aware UTC datetime; naive input is treated as UTC so
    mixed-source evidence never crashes on aware/naive comparison."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _print_result(result: RCAResult, deploys: dict[str, DeployEvent]) -> None:
    if not result.candidates:
        print("No candidate changes found in the correlation window.")
        print("Either no deploys/changes were supplied, or none fall near the alert.")
        return

    print("\n=== ROOT CAUSE CANDIDATES ===")
    for rank, candidate in enumerate(result.candidates, start=1):
        deploy = deploys[candidate.deploy_id]
        b = candidate.confidence
        marker = ">>" if rank == 1 else "  "
        print(f"\n{marker} #{rank}  {candidate.deploy_id}  ({deploy.service}, by {deploy.deployed_by})")
        print(f"     {deploy.diff_summary.get('summary', '')}")
        print(
            f"     confidence {b.composite:.0%}  "
            f"(rules {b.rule_score:.0%} · history {b.rag_score:.0%} · llm {b.llm_adjustment:+.0%})"
        )
        for rule in candidate.rule_hits:
            print(f"       - {rule}: {json.dumps(candidate.evidence.get(rule, {}), default=str)}")
        if "similar_past_incidents" in candidate.evidence:
            for match in candidate.evidence["similar_past_incidents"]:
                print(
                    f"       - precedent: {match['incident_id']} "
                    f"(similarity {match['similarity']}, resolved by {match['resolution']})"
                )
        if "alerts_correlated" in candidate.evidence:
            print(f"       - explains {candidate.evidence['alerts_correlated']} alert(s) in this incident")

    print("\n=== TIMELINE ===")
    for event in result.timeline:
        stamp = event["occurred_at"]
        stamp = stamp.strftime("%H:%M:%S") if hasattr(stamp, "strftime") else str(stamp)
        print(f"  {stamp}  {event['type']:<17} {event['ref']}")


def cmd_demo(args: argparse.Namespace) -> int:
    if args.scenario == "list" or args.scenario is None:
        print("Available simulated incidents (services/correlation-engine/.../scenarios/README.md):\n")
        for scenario in ALL_SCENARIOS:
            print(f"  {scenario.id:<22} {scenario.difficulty.value:<7} {scenario.name}")
        print("\nRun one with: culprit demo <id>")
        return 0

    try:
        scenario = get(args.scenario)
    except KeyError:
        print(f"Unknown scenario '{args.scenario}'. Try: culprit demo list", file=sys.stderr)
        return 2

    # Leave-one-out memory: precedent comes only from OTHER incidents, the
    # same honest setup as the web UI's export.
    memory = IncidentMemory()
    for other in ALL_SCENARIOS:
        if other.id != scenario.id:
            memory.learn_from_scenario(other)
    result = run_scenario(scenario, memory)

    print(f"SIMULATED INCIDENT: {scenario.name}")
    print(f"  {scenario.description}\n")
    for alert in scenario.evidence.alerts:
        print(f"ALERT [{alert.severity}] {alert.title}")
    _print_result(result, {d.id: d for d in scenario.evidence.deploys})

    top = result.top_candidate
    verdict = "correct" if top.deploy_id == scenario.ground_truth.root_cause_deploy_id else "WRONG"
    print(f"\nGROUND TRUTH: {scenario.ground_truth.root_cause_deploy_id} — pipeline verdict is {verdict}.")
    print(f"  ({scenario.ground_truth.explanation})")
    if scenario.expected_rollback:
        print(f"  proposed fix: {scenario.expected_rollback}")
    return 0 if verdict == "correct" else 1


def _load_json(path: str):
    # Clean errors at the trust boundary: `diagnose` runs on files a design
    # partner exported, so a missing/garbled file must say so plainly, not
    # traceback.
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"input error: file not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"input error: {path} is not valid JSON ({exc})")


def _parse_ts(value: str, what: str) -> datetime:
    try:
        return _ts(value)
    except (ValueError, TypeError):
        raise SystemExit(f"input error: {what} is not an ISO-8601 timestamp: {value!r}")


def cmd_diagnose(args: argparse.Namespace) -> int:
    deploys: list[DeployEvent] = []
    for i, item in enumerate(_load_json(args.deploys_file)):
        if not isinstance(item, dict) or "service" not in item or "occurred_at" not in item:
            raise SystemExit(
                f"input error: {args.deploys_file} entry {i}: each deploy needs "
                "'service' and 'occurred_at'")
        deploys.append(DeployEvent(
            id=item.get("id") or item.get("sha") or f"deploy-{i}",
            service=item["service"],
            source=item.get("source", "import"),
            git_sha=item.get("sha"),
            diff_summary={"summary": item.get("summary", ""), "files_changed": item.get("files_changed", [])},
            deployed_by=item.get("deployed_by", "unknown"),
            occurred_at=_parse_ts(item["occurred_at"], f"{args.deploys_file} entry {i} 'occurred_at'"),
        ))

    k8s_events = ()
    if args.events_file:
        raw = _load_json(args.events_file)
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        try:
            k8s_events = tuple(parse_k8s_event(item) for item in items)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            # AttributeError covers the wrong-shape cases: an events file that
            # is an object without `items`, or a list of non-objects, hands
            # parse_k8s_event a string whose .get() blows up.
            raise SystemExit(
                f"input error: {args.events_file} — expected `kubectl get events -o json` "
                f"output or a list of Event objects ({type(exc).__name__})")

    edges = ()
    if args.edges_file:
        parsed_edges = []
        for j, item in enumerate(_load_json(args.edges_file)):
            if not isinstance(item, dict) or "from" not in item or "to" not in item:
                raise SystemExit(
                    f"input error: {args.edges_file} entry {j}: each edge needs 'from' and 'to'")
            parsed_edges.append(ServiceEdge(item["from"], item["to"], item.get("type", "depends_on")))
        edges = tuple(parsed_edges)

    alert = AlertEvent(
        id="alert-cli-1",
        service=args.alert_service,
        title=args.alert_title,
        severity=args.severity,
        fired_at=_parse_ts(args.fired_at, "--fired-at"),
    )

    bundle = EvidenceBundle(
        deploys=tuple(deploys), alerts=(alert,), k8s_events=k8s_events, service_edges=edges,
    )
    graph = KnowledgeGraph.from_edges(bundle.service_edges)
    with _open_memory(args) as memory:
        result = RCAResult(
            candidates=rank_candidates(bundle, graph, memory),
            timeline=build_timeline(bundle),
        )
        print(f"ALERT [{alert.severity}] {alert.title}  (service: {alert.service})")
        _print_result(result, {d.id: d for d in deploys})
        if memory is None:
            print("\nNote: running without incident memory — precedent scoring is off.")
            print("Pass --memory-dsn (and record confirmed incidents with `culprit learn`)")
            print("to activate it. Confidence is rule-evidence only, by design.")
        else:
            print(f"\nIncident memory: {args.memory_backend} backend, {len(memory)} resolved incident(s).")

    # LLM explanation runs after the DB connection is released — the model
    # call is the slow part, and it needs the finished result, not memory.
    if getattr(args, "explain", False):
        _explain_and_print(result)
    return 0


def _default_explainer_model():
    """The production explainer model, or None if unavailable. Kept as a
    seam so tests inject a ScriptedModel by monkeypatching this name."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n[--explain] set ANTHROPIC_API_KEY to enable LLM explanations; "
              "showing the deterministic verdict only.", file=sys.stderr)
        return None
    from ai_reasoning.model import AnthropicModel

    return AnthropicModel()


def _explain_and_print(result: RCAResult) -> None:
    """Lazily invoke the LLM explanation layer on top of the finished
    deterministic verdict. Every failure path degrades to nothing printed:
    the deterministic answer stands alone — that is the architecture, not a
    fallback (docs/07-ai-architecture.md). ai_reasoning imports FROM
    correlation_engine, so this import stays lazy to avoid a package cycle
    and to keep the credential-free CLI free of the dependency."""
    try:
        from ai_reasoning.explain import explain
    except ImportError:
        print("\n[--explain] the ai-reasoning package isn't importable "
              "(install services/ai-reasoning); deterministic verdict stands.",
              file=sys.stderr)
        return

    model = _default_explainer_model()
    if model is None:
        return

    explanation = explain(result, model)
    if explanation is None:
        return

    print("\n=== AI EXPLANATION (grounded in the evidence above) ===")
    print(explanation.narrative)
    if explanation.confidence is not None:
        print(
            f"\ncalibrated confidence for {explanation.top_candidate_id}: "
            f"{explanation.confidence.composite:.0%} "
            f"(LLM adjustment {explanation.confidence.llm_adjustment:+.0%}, bounded to +/-15%)"
        )
    if explanation.citations:
        print(f"cited evidence: {', '.join(explanation.citations)}")
    if explanation.stripped_citations:
        print("guardrail stripped ungrounded citations: "
              f"{', '.join(explanation.stripped_citations)}")
    if not explanation.grounded:
        print("(explanation not fully grounded — confidence NOT boosted; "
              "the deterministic verdict is authoritative)")


@contextlib.contextmanager
def _open_memory(args):
    """Persistent memory (or None), as a context manager so the DB
    connection is closed deterministically on exit. The CLI is short-lived,
    but a leaked handle is a leaked handle — and this exact code moves into
    the long-lived Phase 2 service, where it would matter. psycopg loads
    lazily so the credential-free demo/diagnose path stays dependency-free."""
    if not getattr(args, "memory_dsn", None):
        yield None
        return
    import psycopg

    from .db.postgres import PgVectorIncidentMemory, PostgresIncidentMemory, apply_schema

    conn = psycopg.connect(args.memory_dsn, autocommit=True)
    try:
        apply_schema(conn)
        if args.memory_backend == "pgvector":
            yield PgVectorIncidentMemory(conn, _build_embedder(args.embedder))
        else:
            yield PostgresIncidentMemory(conn)
    finally:
        conn.close()


def _build_embedder(kind: str):
    import os

    from .embeddings import HashingEmbedder, VoyageEmbedder

    if kind == "voyage":
        key = os.environ.get("VOYAGE_API_KEY")
        if not key:
            raise SystemExit("--embedder voyage requires the VOYAGE_API_KEY environment variable")
        return VoyageEmbedder(key)
    return HashingEmbedder()


def cmd_learn(args: argparse.Namespace) -> int:
    with _open_memory(args) as memory:
        if memory is None:
            print("learn requires --memory-dsn (there is nowhere else to persist).", file=sys.stderr)
            return 2

        if args.from_scenario:
            ids = (
                [s.id for s in ALL_SCENARIOS]
                if args.from_scenario == "all"
                else [args.from_scenario]
            )
            for sid in ids:
                memory.learn_from_scenario(get(sid))
            print(f"learned {len(ids)} incident(s); memory now holds {len(memory)}.")
            return 0

        required = (args.incident_id, args.title, args.culprit_service, args.root_cause, args.resolution)
        if not all(required):
            print(
                "learn needs either --from-scenario, or all of --incident-id "
                "--title --culprit-service --root-cause --resolution.",
                file=sys.stderr,
            )
            return 2
        from .memory import ResolvedIncident

        memory.learn(ResolvedIncident(
            incident_id=args.incident_id,
            title=args.title,
            culprit_service=args.culprit_service,
            root_cause_summary=args.root_cause,
            resolution=args.resolution,
        ))
        print(f"learned '{args.incident_id}'; memory now holds {len(memory)}.")
        return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from .evaluation import evaluate, format_report

    metrics = evaluate()
    print(format_report(metrics))

    if getattr(args, "memory_dsn", None):
        import psycopg

        from .db.postgres import apply_schema
        from .evaluation import compare_backends, format_comparison

        conn = psycopg.connect(args.memory_dsn, autocommit=True)
        apply_schema(conn)
        try:
            comparison = compare_backends(conn, _build_embedder(args.embedder))
        finally:
            conn.close()
        print("\n" + format_comparison(comparison))

    # The SPEC gate, enforced at the exit code so CI fails loudly if the
    # RAG layer ever starts subtracting signal. The backend comparison is
    # informational — adoption is an operator decision on real data.
    return 0 if metrics["warm"]["p1"] >= metrics["rule_only_baseline_p1"] else 1


def _add_memory_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--memory-dsn",
                        help="Postgres DSN for persistent incident memory (schema applied automatically)")
    parser.add_argument("--memory-backend", choices=("lexical", "pgvector"), default="lexical",
                        help="lexical (default — see memory.py's eval-gating note) or pgvector (SQL cosine retrieval)")
    parser.add_argument("--embedder", choices=("hash", "voyage"), default="hash",
                        help="pgvector backend only: hash (deterministic, offline) or voyage (semantic; needs VOYAGE_API_KEY)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="culprit", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="run a simulated incident through the real pipeline")
    demo.add_argument("scenario", nargs="?", default=None, help="scenario id, or 'list'")
    demo.set_defaults(func=cmd_demo)

    diag = sub.add_parser("diagnose", help="run the pipeline on your own evidence files")
    diag.add_argument("--alert-title", required=True, help="the alert's title, verbatim")
    diag.add_argument("--alert-service", required=True, help="service the alert fired on")
    diag.add_argument("--fired-at", required=True, help="ISO-8601 time the alert fired")
    diag.add_argument("--severity", default="high")
    diag.add_argument("--deploys-file", required=True,
                      help="JSON list: {service, occurred_at, summary, sha?, deployed_by?, files_changed?}")
    diag.add_argument("--events-file",
                      help="output of `kubectl get events -o json` (or a bare list of Event objects)")
    diag.add_argument("--edges-file",
                      help="JSON list: {from, to, type?} service-dependency edges")
    diag.add_argument("--explain", action="store_true",
                      help="add an LLM explanation on top of the verdict "
                           "(needs ANTHROPIC_API_KEY + the ai-reasoning package; "
                           "the deterministic verdict is unaffected)")
    _add_memory_args(diag)
    diag.set_defaults(func=cmd_diagnose)

    learn = sub.add_parser(
        "learn",
        help="record a confirmed incident into persistent memory (feeds future precedent)",
    )
    _add_memory_args(learn)
    learn.add_argument("--from-scenario",
                       help="seed from a harness scenario id, or 'all' for the full catalog")
    learn.add_argument("--incident-id")
    learn.add_argument("--title", help="the alert title(s), verbatim")
    learn.add_argument("--culprit-service")
    learn.add_argument("--root-cause", help="the confirmed root-cause summary")
    learn.add_argument("--resolution", help="what fixed it, e.g. pr_revert:svc:sha")
    learn.set_defaults(func=cmd_learn)

    evalp = sub.add_parser("eval", help="golden-set evaluation report (per-layer + per-rule precision)")
    evalp.add_argument("--memory-dsn",
                       help="also compare lexical vs pgvector memory on the golden set "
                            "(isolated + rolled back; never touches recorded incidents)")
    evalp.add_argument("--embedder", choices=("hash", "voyage"), default="hash",
                       help="embedder for the pgvector side of the comparison")
    evalp.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
