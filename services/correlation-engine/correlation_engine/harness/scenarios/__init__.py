from ..schema import Scenario
from . import (
    alert_storm,
    broken_scraping,
    mesh_routing,
    network_policy_block,
    dns_failure,
    feature_flag_failure,
    missing_metrics,
    terraform_drift,
    terraform_iam_break,
    bad_configmap,
    bad_rollout,
    bad_secret,
    crash_loop_backoff,
    deadlock,
    image_pull_backoff,
    oom_killed,
    pool_exhaustion,
    slow_query,
)

_BUILDERS = (
    pool_exhaustion.build,
    crash_loop_backoff.build,
    oom_killed.build,
    image_pull_backoff.build,
    bad_configmap.build,
    bad_secret.build,
    bad_rollout.build,
    deadlock.build,
    slow_query.build,
    alert_storm.build,
    terraform_iam_break.build,
    terraform_drift.build,
    dns_failure.build,
    feature_flag_failure.build,
    missing_metrics.build,
    broken_scraping.build,
    mesh_routing.build,
    network_policy_block.build,
)

ALL_SCENARIOS: tuple[Scenario, ...] = tuple(builder() for builder in _BUILDERS)


def get(scenario_id: str) -> Scenario:
    for scenario in ALL_SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"no registered scenario '{scenario_id}' — see scenarios/README.md")
