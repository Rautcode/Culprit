#!/usr/bin/env bash
# Seed the good-first-issues backlog (docs/good-first-issues.md) into GitHub:
# creates the labels, then the 11 issues, in one run.
#
# Requires the GitHub CLI, authenticated:  gh auth login
# Run from the repo root:                  bash scripts/seed-issues.sh
#
# Re-running RECREATES the issues (GitHub has no natural dedupe key for issue
# titles), so a second run makes duplicates. Labels use -f and are safe to
# re-run. The script warns and asks before creating issues if any already exist.
set -euo pipefail

command -v gh >/dev/null 2>&1 || { echo "error: gh (GitHub CLI) not installed."; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "error: not authenticated — run 'gh auth login'."; exit 1; }

echo "Repo: $(gh repo view --json nameWithOwner --jq .nameWithOwner)"

# --- Labels (idempotent) -----------------------------------------------------
echo "Creating labels..."
gh label create "good first issue" -c 7057ff -d "Good for newcomers" -f
gh label create "help wanted"      -c 008672 -d "Extra attention is welcomed" -f
gh label create "enhancement"      -c a2eeef -d "New feature or request" -f
gh label create "bug"              -c d73a4a -d "Something isn't working" -f
gh label create "documentation"    -c 0075ca -d "Improvements or additions to documentation" -f
gh label create "testing"          -c fbca04 -d "Adds or improves test coverage" -f
gh label create "scenario"         -c 5319e7 -d "Adds or changes an incident simulation harness scenario" -f

# --- Dedupe guard ------------------------------------------------------------
existing="$(gh issue list --state all --limit 1 --json number --jq 'length')"
if [ "$existing" != "0" ]; then
  read -r -p "This repo already has issues. Create the 11 seed issues anyway (may duplicate)? [y/N] " ans
  [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "Aborted; labels created, no issues added."; exit 0; }
fi

# --- Issues ------------------------------------------------------------------
issue() { gh issue create --title "$1" --label "$2" --body "$3"; }

echo "Creating issues..."

issue "Add a harness scenario: TLS certificate expiry" "good first issue,scenario,help wanted" \
"A cert-renewal deploy ships a cert with the wrong SAN; downstream mTLS handshakes start failing. Copy \`bad_secret.py\` as a template and register \`build()\` in \`scenarios/__init__.py\`.

**Files:** services/correlation-engine/correlation_engine/harness/scenarios/
**Acceptance:** \`pytest\` passes; the parametrized suite ranks the culprit #1 over a decoy. See CONTRIBUTING.md -> \"Add a harness scenario\"."

issue "Add a harness scenario: readiness-probe misconfiguration" "good first issue,scenario" \
"A deploy tightens a readiness probe (path/port/timeout) so pods never go Ready and traffic is withheld -- healthy app, broken rollout.

**Files:** services/correlation-engine/correlation_engine/harness/scenarios/
**Acceptance:** culprit ranked #1 with diff_keyword_match evidence on the probe change; a decoy present and ranked below."

issue "culprit diagnose --json: machine-readable output" "enhancement,help wanted" \
"\`diagnose\` prints a human-readable verdict only. A \`--json\` flag emitting ranked candidates + evidence + confidence would let people pipe Culprit into other tooling.

**Files:** services/correlation-engine/correlation_engine/cli.py (cmd_diagnose, _print_result)
**Do:** reuse the structure scripts/export_incidents.py already produces.
**Acceptance:** \`--json\` prints valid JSON; a test asserts the shape; human output unchanged without the flag."

issue "culprit diagnose --alert-file: read an Alertmanager webhook" "enhancement,good first issue" \
"Today the alert comes from --alert-title/--alert-service/--fired-at flags. An \`--alert-file\` reading an Alertmanager webhook JSON would reuse the existing adapter.

**Files:** cli.py; adapter already exists at collection/adapters.py::parse_alertmanager
**Acceptance:** --alert-file populates the alert from a real payload; a test covers it; the flag form still works."

issue "Support GitLab deployment webhooks in the adapter" "enhancement,help wanted" \
"collection/adapters.py parses GitHub \`deployment\` webhooks only. GitLab is the other common source.

**Do:** add parse_gitlab_deployment(payload) mirroring parse_github_deployment, mapping GitLab deployment webhook fields.
**Acceptance:** a unit test in tests/test_collection.py with a real GitLab payload shape produces a correct DeployEvent."

issue "Web UI: light theme" "enhancement,good first issue" \
"The UI is dark-only; docs/08-ui-design.md specifies light support via prefers-color-scheme plus a manual toggle.

**Files:** apps/web/app/ (Tailwind classes, globals.css)
**Acceptance:** incident list and detail render correctly in light mode; a visible toggle; respects the system preference by default."

issue "Web UI: accessibility pass on the incident detail" "enhancement,help wanted" \
"docs/08-ui-design.md promises keyboard navigation and an ARIA live region; the current detail view needs an a11y pass.

**Acceptance:** the \"Why N%?\" disclosures are keyboard-operable; evidence and timeline have sensible landmarks/labels; passes an axe check."

issue "Unit-test the VoyageEmbedder retry path" "testing,good first issue" \
"embeddings.py::VoyageEmbedder._post_with_retry retries on 429/5xx with backoff but is not covered by a test (it needs a network + key in real use).

**Do:** mock urllib.request.urlopen to raise HTTPError(429) twice then succeed; assert it retries and returns the payload; assert a 400 fails fast.
**Acceptance:** a test exercises retry + fast-fail with no network."

issue "Test build_timeline chronological ordering with tied timestamps" "testing,good first issue" \
"pipeline.py::build_timeline sorts events by time; there is no test for the edge case where a deploy and an alert share a timestamp (the seeded demo actually hits this).

**Acceptance:** a test constructs same-timestamp events and asserts a stable, sensible order."

issue "Docs: a per-rule reference page" "documentation,good first issue" \
"The five rules are documented inline and in docs/07; a single reference page (what each rule scores, its inputs, its evidence shape, an example) would help contributors and users.

**Do:** add docs/rules-reference.md, one section per rule in ranking/rules.py.
**Acceptance:** all 5 rules documented with a worked example; linked from the README and docs/07."

issue "Add a CHANGELOG.md" "documentation,good first issue" \
"Releases are tagged but there is no changelog. Start one from the v0.1.0 notes.

**Do:** add CHANGELOG.md (Keep a Changelog format); seed [0.1.0] from docs/releases/v0.1.0.md.
**Acceptance:** a changelog exists and is linked from the README."

echo "Done. Created labels + 11 issues."
