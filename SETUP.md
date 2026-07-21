# SETUP — go-live checklist

The operator's runbook for taking Culprit from its current state (every
build step implemented and CI-verified) to actually live. Ordered by
dependency: each tier unlocks the next. Everything through Tier 0 runs
today with zero credentials; Tiers 1-5 are the credential-gated unlocks the
build deliberately stopped short of; Tier 6 is the human work that decides
whether any of it matters.

Legend: ☐ to do · ✅ done & CI-verified in the repo · 🔑 needs a credential
you supply · 👤 human action only you can take.

Honesty rule (inherited from the README): a box is only checked when the
thing is verified, not when it's written. The repo ships everything below
as code; this file is about *activating* it.

---

## Tier 0 — Local, zero credentials (verify it runs)

Proves the core loop on your machine in ~2 minutes. Nothing here needs an
account.

- [ ] **Run the pipeline tests + golden-set evaluation**
  ```
  python -m pytest services/correlation-engine/tests services/ai-reasoning/tests -v
  ```
  Verify: 46 passed (1 skipped — the Postgres suite, which activates in
  Tier 1).

- [ ] **See the evaluation metrics**
  ```
  cd services/correlation-engine && python -m correlation_engine.cli eval
  ```
  Verify: composite precision@1 = 100%, and the honest authored-bias
  warning is present (that warning is a feature — see
  [SPEC_VERSION.md](SPEC_VERSION.md) § Evaluation).

- [ ] **Run the demo** (the Phase 0 first-conversation artifact)
  ```
  python -m correlation_engine.cli demo list
  python -m correlation_engine.cli demo deadlock
  ```
  Verify: verdict is "correct", evidence cited per rule.

- [ ] **Install the `culprit` console command** (optional convenience)
  ```
  pip install -e services/correlation-engine
  culprit demo broken_scraping
  ```

- [ ] **Run the web UI**
  ```
  cd apps/web && npm install && npm run dev     # http://localhost:3000/incidents
  ```

- [ ] **(Optional) local backing services** for Tier 1 without a managed DB
  ```
  docker-compose up -d     # postgres+pgvector, redis, redpanda, minio
  ```

---

## Tier 1 — Persistent incident memory (Postgres) 🔑

Unlocks: memory that survives restarts, and the `learn` → `diagnose`
feedback loop that makes precedent compound. Without this, memory is
per-process only.

Credential: a Postgres connection string. Local compose gives you one for
free (`postgresql://culprit:culprit@localhost:5432/culprit`); production
wants a managed instance with the `pgvector` extension.

- [ ] **Point the CLI at a database** (schema applies automatically)
  ```
  export CULPRIT_DSN=postgresql://culprit:culprit@localhost:5432/culprit
  culprit learn --memory-dsn "$CULPRIT_DSN" --from-scenario all
  ```
  Verify: "memory now holds 18".

- [ ] **Confirm precedent shows up in a diagnosis**
  ```
  culprit diagnose --memory-dsn "$CULPRIT_DSN" \
    --alert-title "DB connection pool exhausted" --alert-service checkout-service \
    --fired-at 2026-07-22T09:32:30Z --deploys-file <your-deploys.json>
  ```
  Verify: the top candidate's evidence includes a `precedent:` line.

- [ ] **The real workflow**: after each real incident, record what actually
  fixed it, so the next one cites it —
  ```
  culprit learn --memory-dsn "$CULPRIT_DSN" \
    --incident-id inc-2026-07-22 --title "<the alert title>" \
    --culprit-service <svc> --root-cause "<confirmed cause>" \
    --resolution "<what fixed it>"
  ```

---

## Tier 2 — Semantic embeddings (Voyage) 🔑

Unlocks: precedent matching on *meaning* rather than shared words. The
default lexical backend works without this; the pgvector backend with a
real embedder is the upgrade — **gated on the eval comparison**, not on
novelty (see the note in `embeddings.py`).

Credential: a [Voyage AI](https://www.voyageai.com/) API key (Anthropic has
no embeddings endpoint; Voyage is the recommended partner).

- [ ] **Run the golden set through both backends and compare** before
  switching the default. Only adopt embeddings if precision improves:
  ```
  export VOYAGE_API_KEY=...
  culprit diagnose --memory-dsn "$CULPRIT_DSN" \
    --memory-backend pgvector --embedder voyage  ...
  ```
  Verify: it retrieves precedent (fails loudly if the key is missing).

- [ ] **If adopted**: add an `ivfflat` index on the embedding columns (the
  named next trigger in `schema.sql`) once row counts justify it.

---

## Tier 3 — Live LLM explanations (Anthropic) 🔑

Unlocks: prose "why this is the cause" on top of the deterministic verdict.
The wiring is done — `culprit diagnose --explain` calls `ai_reasoning.explain`
behind the grounding guardrail (CI-tested via a scripted model; it degrades
cleanly to the deterministic verdict when the package or key is absent).
Only the key remains.

Credential: an `ANTHROPIC_API_KEY` (the production `AnthropicModel`
defaults to `claude-opus-4-8`).

- [ ] Install the LLM layer alongside the CLI so `--explain` can import it:
  ```
  pip install -e services/correlation-engine -e services/ai-reasoning
  ```
- [ ] Set `ANTHROPIC_API_KEY`, then:
  ```
  culprit diagnose --explain --alert-title "..." --alert-service ... \
    --fired-at ... --deploys-file ...
  ```
  Verify: an `AI EXPLANATION` section appears; any citation the model
  invents is stripped and flagged, and confidence stays within ±15% of the
  deterministic value (the guardrail, visible in the output).

- [ ] **Rehearse it before showing a partner.** This exact command is
  **Beat 2.5** of the demo script
  ([docs/validation/04-demo-script.md](docs/validation/04-demo-script.md)) —
  its Setup block preps a fixture and the talk track sells the guardrail
  (the bounded adjustment + stripped citations). If the guardrail line
  doesn't appear when you rehearse, that beat is skipped, not improvised.

---

## Tier 4 — Cloud deployment (AWS EKS) 🔑

Unlocks: the app running on a real cluster, reachable, deployed by CI.
Everything is written and `terraform validate`-clean; only `apply` is
pending. **This bills a real AWS account.**

Credential: AWS credentials with permission to create VPC/EKS/ECR/IAM.
Verify first: `aws sts get-caller-identity` must succeed (it currently
returns `InvalidClientTokenId` on this machine — that is the gate).

- [ ] **Provision** (~15-20 min for the control plane)
  ```
  cd infra/terraform/environments/dev
  terraform init
  terraform apply
  ```

- [ ] **Wire CI to the cluster** (values are `terraform output`s)
  ```
  gh variable set AWS_ROLE_ARN     -b "$(terraform output -raw github_deploy_role_arn)"
  gh variable set AWS_REGION       -b ap-south-1
  gh variable set EKS_CLUSTER_NAME -b "$(terraform output -raw cluster_name)"
  ```
  Setting `AWS_ROLE_ARN` is the switch that activates
  `.github/workflows/deploy.yml` (inert until then).

- [ ] **Deploy** — push to `apps/web/**` or run the `deploy` workflow
  manually (type `deploy` to confirm). Verify: the workflow's rollout step
  lists a Ready deployment.

- [ ] **Migrate Terraform state** to S3 + DynamoDB lock (see `backend.tf`)
  the moment a second operator exists.

- [ ] **Teardown when done**: `terraform destroy` (stops the bill).

Full detail: [infra/terraform/environments/dev/README.md](infra/terraform/environments/dev/README.md).

---

## Tier 5 — GitOps (ArgoCD) 🔑 — optional, on top of Tier 4

Unlocks: git-as-source-of-truth deploys instead of push-deploys — the
deploy-metadata trail Culprit itself is designed to consume.

- [ ] Install ArgoCD on the cluster.
- [ ] Point the image in `infra/helm/culprit-platform/values.yaml` at the
  ECR repo (`terraform output ecr_repository_url`).
- [ ] `kubectl apply -f infra/k8s/argocd/culprit-platform-app.yaml`.
- [ ] Verify: the Application syncs and self-heals.

---

## Tier 6 — Phase 0 validation 👤 — the gate that actually matters

None of Tiers 1-5 prove the product is *wanted*. This does, and only you
can do it. Kit is in [docs/validation/](docs/validation/).

- [ ] **Post the problem-statement drafts** (r/sre, r/devops, r/kubernetes,
  CNCF Slack) — [docs/validation/02-problem-statement-posts.md](docs/validation/02-problem-statement-posts.md).
  Problem only, no product, no repo link.
- [ ] **Book 8-10 interviews** — [the guide](docs/validation/01-interview-guide.md).
- [ ] **Demo the CLI** to the strongest 3-5 — [the script](docs/validation/04-demo-script.md).
  Beats 1-3 need no credentials; the optional **Beat 2.5** (LLM narration,
  guardrail on show) needs Tier 3's key rehearsed the morning of — skip it
  otherwise.
- [ ] **Log everything same-day** in [the tracker](docs/validation/03-candidate-tracker.md),
  and run the **kill-signal check**: if pain isn't described unprompted, or
  a named tool already solves it, that finding is a successful Phase 0 too.
- [ ] **Record real-incident precision@1** in SPEC_VERSION.md — the last
  unfilled Phase 1 exit criterion. No number until it's real data.

---

## Where the line is right now

Tier 0 is green in CI on every push. Tiers 1-5 are written, validated, and
waiting on the credentials named in each. Tier 6 is where a working system
becomes a validated one — and it starts with a post you write, not a
command you run.
