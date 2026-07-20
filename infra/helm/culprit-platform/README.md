# culprit-platform chart

Build step 9 (SPEC_VERSION.md). Deploys Culprit's own services — Phase 1
deployable: the web UI (real pipeline output baked at image build).

Verified on every push by the `deploy-verify` CI job: container build ->
kind cluster -> `helm install --wait` -> HTTP through the Service. EKS is
the same chart behind the ALB ingress (`web.ingress.enabled=true`) synced
by ArgoCD (infra/k8s/argocd/) — pending AWS access.

Local run (needs Docker + kind + helm):

```
docker build -t culprit-web:dev apps/web
kind create cluster --name culprit
kind load docker-image culprit-web:dev --name culprit
helm install culprit infra/helm/culprit-platform
kubectl port-forward svc/culprit-web 8080:80   # http://localhost:8080/incidents
```
