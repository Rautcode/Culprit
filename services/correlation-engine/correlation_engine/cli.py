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
            retrieval via embeddings.py).

  learn     Record a confirmed incident into persistent memory — the
            "Learn" step of the core loop, closing the feedback cycle so
            future diagnose runs cite it as precedent. Seed a demo store
            with --from-scenario all.

Run as `python -m correlation_engine.cli ...` from services/correlation-engine,
or `culprit ...` after `pip install -e services/correlation-engine`.
"""
from __future__ import annotations

import argparse
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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_diagnose(args: argparse.Namespace) -> int:
    deploys: list[DeployEvent] = []
    for i, item in enumerate(_load_json(args.deploys_file)):
        deploys.append(DeployEvent(
            id=item.get("id") or item.get("sha") or f"deploy-{i}",
            service=item["service"],
            source=item.get("source", "import"),
            git_sha=item.get("sha"),
            diff_summary={"summary": item.get("summary", ""), "files_changed": item.get("files_changed", [])},
            deployed_by=item.get("deployed_by", "unknown"),
            occurred_at=_ts(item["occurred_at"]),
        ))

    k8s_events = ()
    if args.events_file:
        raw = _load_json(args.events_file)
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        k8s_events = tuple(parse_k8s_event(item) for item in items)

    edges = ()
    if args.edges_file:
        edges = tuple(
            ServiceEdge(item["from"], item["to"], item.get("type", "depends_on"))
            for item in _load_json(args.edges_file)
        )

    alert = AlertEvent(
        id="alert-cli-1",
        service=args.alert_service,
        title=args.alert_title,
        severity=args.severity,
        fired_at=_ts(args.fired_at),
    )

    bundle = EvidenceBundle(
        deploys=tuple(deploys), alerts=(alert,), k8s_events=k8s_events, service_edges=edges,
    )
    graph = KnowledgeGraph.from_edges(bundle.service_edges)
    memory = _open_memory(args)
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
    return 0


def _open_memory(args):
    """Persistent memory, or None. psycopg loads lazily so the
    credential-free demo/diagnose path stays dependency-free."""
    if not getattr(args, "memory_dsn", None):
        return None
    import os

    import psycopg

    from .db.postgres import PgVectorIncidentMemory, PostgresIncidentMemory, apply_schema

    conn = psycopg.connect(args.memory_dsn, autocommit=True)
    apply_schema(conn)
    if args.memory_backend == "pgvector":
        from .embeddings import HashingEmbedder, VoyageEmbedder

        if args.embedder == "voyage":
            key = os.environ.get("VOYAGE_API_KEY")
            if not key:
                raise SystemExit("--embedder voyage requires the VOYAGE_API_KEY environment variable")
            embedder = VoyageEmbedder(key)
        else:
            embedder = HashingEmbedder()
        return PgVectorIncidentMemory(conn, embedder)
    return PostgresIncidentMemory(conn)


def cmd_learn(args: argparse.Namespace) -> int:
    memory = _open_memory(args)
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
