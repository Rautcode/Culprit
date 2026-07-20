# infra/k8s/argocd

GitOps definitions (docs/09-infrastructure.md "Delivery").

- [`culprit-platform-app.yaml`](culprit-platform-app.yaml) — the ArgoCD
  Application tracking `infra/helm/culprit-platform` on `main`. Apply-ready;
  not yet applied — needs an ArgoCD install on a real cluster, which is
  blocked on EKS/AWS access. Local verification uses `helm install` on a
  kind cluster instead (see the chart's README and CI).
