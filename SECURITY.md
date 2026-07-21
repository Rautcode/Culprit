# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for a security vulnerability.

Report it privately by email to **manav.p.raut27@gmail.com** with:

- a description of the issue and its impact,
- steps to reproduce (or a proof of concept),
- the affected file(s)/commit if known.

This is a pre-1.0, single-maintainer project — there's no formal SLA, but
you'll get an acknowledgement and a good-faith effort to triage and fix.
Please allow reasonable time to address an issue before any public
disclosure.

## Supported versions

Pre-1.0: only the latest `main` is supported. There are no backported
security fixes to tagged releases yet.

## Security posture (what's already in place)

For context on what a report would be measured against — the codebase was
reviewed for these and they hold today:

- **SQL:** every query is parameterized (psycopg placeholders); no dynamic
  SQL from user input. The pgvector literal is float-formatted *and* bound.
- **Web:** no `dangerouslySetInnerHTML`, no `eval`; React escapes all
  rendered values.
- **Secrets:** API keys and DSNs are read from environment variables, never
  logged and never committed. The database schema stores `secret_ref`
  pointers, not secrets.
- **Input boundary:** the `culprit diagnose` command validates
  partner-supplied files and fails with a clean message rather than
  exposing a stack trace.
- **Container:** the web image runs as a non-root numeric user; the Helm
  chart sets `runAsNonRoot`, resource limits, and probes.

## Out of scope (not built yet)

Auth (JWT/RBAC), an HTTP API surface, rate limiting, and multi-tenant
isolation are **designed but not implemented** (see [docs/](docs/)) — there
is no running server to attack in this release. Reports about the *designed*
SaaS surface are welcome as design feedback, but aren't vulnerabilities in
shipped code.
