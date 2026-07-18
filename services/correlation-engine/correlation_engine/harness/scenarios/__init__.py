from ..schema import Scenario
from . import crash_loop_backoff, image_pull_backoff, oom_killed, pool_exhaustion

_BUILDERS = (
    pool_exhaustion.build,
    crash_loop_backoff.build,
    oom_killed.build,
    image_pull_backoff.build,
)

ALL_SCENARIOS: tuple[Scenario, ...] = tuple(builder() for builder in _BUILDERS)


def get(scenario_id: str) -> Scenario:
    for scenario in ALL_SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    raise KeyError(f"no registered scenario '{scenario_id}' — see scenarios/README.md")
