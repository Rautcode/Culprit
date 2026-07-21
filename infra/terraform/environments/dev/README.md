# dev environment — EKS + ECR + CI deploy role

The cloud half of build step 9 (docs/09-infrastructure.md). Provisions a
small non-prod EKS cluster, an ECR repo for the web image, and the GitHub
OIDC role that `.github/workflows/deploy.yml` assumes — no long-lived AWS
keys anywhere.

**Applying this bills a real AWS account** (~one t3.medium node pair, one
NAT gateway, one EKS control plane). It is a deliberate operator action,
not something CI runs. CI only checks `terraform fmt` and `validate`.

## First apply

Needs valid AWS credentials (`aws sts get-caller-identity` must succeed)
and Terraform ≥ 1.5.

```
cd infra/terraform/environments/dev
terraform init
terraform apply          # ~15-20 min for the EKS control plane

# Wire CI to the cluster (outputs from the apply):
gh variable set AWS_ROLE_ARN     -b "$(terraform output -raw github_deploy_role_arn)"
gh variable set AWS_REGION       -b ap-south-1
gh variable set EKS_CLUSTER_NAME -b "$(terraform output -raw cluster_name)"
```

Setting `AWS_ROLE_ARN` is the switch that activates
`.github/workflows/deploy.yml` — until then it skips cleanly.

## After it's up

- Push to `apps/web/**` or `infra/helm/**` triggers `deploy.yml`
  (build → ECR → `helm upgrade`), or run it manually via the Actions tab
  (type `deploy` to confirm).
- For GitOps instead of push-deploy, install ArgoCD and apply
  `infra/k8s/argocd/culprit-platform-app.yaml`, pointing `values` image at
  the ECR repo.

## Teardown

```
terraform destroy
```

## State

Local state for the first apply (backend.tf explains the bootstrap
chicken-and-egg). Migrate to the S3 backend + DynamoDB lock the moment a
second operator exists — local state on one laptop is fine exactly until
then.
