# Good first issues — seed list

A curated backlog of real, approachable tasks grounded in the current
codebase (not generic filler). Each block below is ready to paste into
GitHub's **New Issue** form: the heading is the title, the labels line is
what to apply, and the body follows. Delete this file once the issues are
created, or keep it as a public backlog — your call.

Suggested labels to create first (Issues → Labels):
`good first issue` · `help wanted` · `documentation` · `enhancement` ·
`bug` · `testing` · `scenario`

---

## Add a `.gitattributes` to normalize line endings
**Labels:** `good first issue` `enhancement`

Every commit on Windows warns "LF will be replaced by CRLF." A
`.gitattributes` at the repo root fixes it repo-wide.

- **Do:** add `.gitattributes` with `* text=auto eol=lf` (and `*.png binary`,
  `*.ico binary` for assets); run `git add --renormalize .`.
- **Acceptance:** fresh clones and commits no longer emit CRLF warnings;
  no file content changes beyond line endings.

---

## Add a harness scenario: TLS certificate expiry
**Labels:** `good first issue` `scenario` `help wanted`

The 18-scenario harness has no "expired certificate" incident — a common,
distinctive failure (works fine until midnight, then every mTLS call fails).

- **Files:** `services/correlation-engine/correlation_engine/harness/scenarios/`
- **Do:** copy `bad_secret.py` as a template; model a cert-renewal deploy
  whose new cert has the wrong SAN, causing downstream TLS handshake
  failures; register `build()` in `scenarios/__init__.py`.
- **Acceptance:** `pytest` passes; the parametrized suite ranks the culprit
  #1 over a decoy. See [CONTRIBUTING.md](../CONTRIBUTING.md) → "Add a harness
  scenario."

---

## Add a harness scenario: readiness-probe misconfiguration
**Labels:** `good first issue` `scenario`

A deploy tightens a readiness probe (path/port/timeout) so pods never go
Ready and traffic is withheld — healthy app, broken rollout.

- **Files:** same as above.
- **Acceptance:** culprit ranked #1 with `diff_keyword_match` evidence on the
  probe change; a decoy present and ranked below.

---

## `culprit diagnose --json`: machine-readable output
**Labels:** `enhancement` `help wanted`

`diagnose` prints a human-readable verdict only. A `--json` flag emitting
the ranked candidates + evidence + confidence breakdown would let people
pipe Culprit into other tooling.

- **Files:** `services/correlation-engine/correlation_engine/cli.py`
  (`cmd_diagnose`, `_print_result`).
- **Do:** add `--json`; serialize the same data `scripts/export_incidents.py`
  already shapes (reuse that structure for consistency).
- **Acceptance:** `--json` prints valid JSON with candidates/evidence/
  timeline; a test asserts the shape; human output unchanged without the flag.

---

## `culprit diagnose --alert-file`: read an Alertmanager webhook
**Labels:** `enhancement` `good first issue`

Today the alert is passed via `--alert-title/--alert-service/--fired-at`
flags. An `--alert-file` that reads an Alertmanager webhook JSON would reuse
the existing adapter and match how people actually have the data.

- **Files:** `cli.py`; the adapter already exists at
  `collection/adapters.py::parse_alertmanager`.
- **Acceptance:** `--alert-file` populates the alert from a real Alertmanager
  payload; a test covers it; the flag form still works.

---

## Support GitLab deployment webhooks in the adapter
**Labels:** `enhancement` `help wanted`

`collection/adapters.py` parses GitHub `deployment` webhooks only. GitLab is
the other common source.

- **Do:** add `parse_gitlab_deployment(payload)` mirroring
  `parse_github_deployment`, mapping GitLab's deployment webhook fields.
- **Acceptance:** a unit test in `tests/test_collection.py` with a real
  GitLab payload shape produces a correct `DeployEvent`.

---

## Web UI: light theme
**Labels:** `enhancement` `good first issue`

The UI is dark-only; `docs/08-ui-design.md` specifies light support via
`prefers-color-scheme` + a manual toggle.

- **Files:** `apps/web/app/` (Tailwind classes, `globals.css`).
- **Acceptance:** the incident list and detail render correctly in light
  mode; a visible toggle; respects the system preference by default.

---

## Web UI: accessibility pass on the incident detail
**Labels:** `enhancement` `help wanted`

`docs/08-ui-design.md` promises keyboard navigation and an ARIA live region
for the (future) streaming pane; the current detail view needs an a11y pass.

- **Acceptance:** the "Why N%?" disclosures are keyboard-operable; evidence
  and timeline have sensible landmarks/labels; passes an axe check.

---

## Unit-test the VoyageEmbedder retry path
**Labels:** `testing` `good first issue`

`embeddings.py::VoyageEmbedder._post_with_retry` retries on 429/5xx with
backoff, but it isn't covered by a test (it needs a network + key in real
use).

- **Do:** mock `urllib.request.urlopen` to raise `HTTPError(429)` twice then
  succeed; assert it retries and returns the payload; assert a 400 fails fast.
- **Acceptance:** a test in `tests/` exercises retry + fast-fail with no
  network.

---

## Test build_timeline chronological ordering with tied timestamps
**Labels:** `testing` `good first issue`

`pipeline.py::build_timeline` sorts events by time; there's no test for the
edge case where a deploy and an alert share a timestamp (the seeded demo
actually hits this).

- **Acceptance:** a test constructs same-timestamp events and asserts a
  stable, sensible order.

---

## Docs: a per-rule reference page
**Labels:** `documentation` `good first issue`

The five rules are documented inline in code and `docs/07`; a single
reference page (what each rule scores, its inputs, its evidence shape, and
an example) would help contributors and users.

- **Do:** add `docs/rules-reference.md`; one section per rule in
  `ranking/rules.py`.
- **Acceptance:** each of the 5 rules documented with a worked example;
  linked from the README and `docs/07`.

---

## Add a CHANGELOG.md
**Labels:** `documentation` `good first issue`

Releases are tagged but there's no changelog. Start one from the v0.1.0
notes.

- **Do:** add `CHANGELOG.md` (Keep a Changelog format); seed `[0.1.0]` from
  `docs/releases/v0.1.0.md`.
- **Acceptance:** a changelog exists and is linked from the README.
