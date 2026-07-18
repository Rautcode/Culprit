"""Rule Engine — v1.0 frozen rule set (SPEC_VERSION.md "v1.0 Rule Engine").

Five named, independently testable rules, each returning (score: float 0-1,
evidence: dict). Not yet implemented — see docs/07-ai-architecture.md
"Rule Engine" for the spec of each rule below.
"""

RULE_NAMES = (
    "time_proximity",
    "ownership_distance",
    "diff_keyword_match",
    "historical_pattern_match",
    "blast_radius_weight",
)
