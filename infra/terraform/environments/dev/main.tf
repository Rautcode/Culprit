# Culprit dev environment — the EKS half of build step 9 (docs/09-infrastructure.md).
#
# Phase 1 sizing per docs/10-roadmap.md: one small non-prod cluster, nothing
# speculative. RDS/Redis/CloudFront/Route53 join when a deployed service
# actually needs them, not before.
#
# Deliberate deviation from the modules/ skeleton: VPC and EKS use the
# battle-tested terraform-aws-modules registry modules instead of bespoke
# wrappers — our own modules/ directories stay for genuinely custom
# concerns. Applying this is a USER action (it bills the AWS account);
# CI verifies fmt + validate only. See README.md alongside this file.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.16"

  name = "${var.cluster_name}-vpc"
  cidr = "10.40.0.0/16"

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = ["10.40.1.0/24", "10.40.2.0/24", "10.40.3.0/24"]
  public_subnets  = ["10.40.101.0/24", "10.40.102.0/24", "10.40.103.0/24"]

  # One NAT gateway, not one per AZ — dev cost posture (docs/09 cost notes).
  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name    = var.cluster_name
  cluster_version = "1.31"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access           = true
  enable_cluster_creator_admin_permissions = true

  eks_managed_node_groups = {
    default = {
      instance_types = ["t3.medium"]
      min_size       = 1
      max_size       = 3
      desired_size   = 2
    }
  }

  # The GitHub Actions deploy role gets cluster admin on THIS dev cluster —
  # acceptable for dev; prod narrows this to a namespace-scoped policy.
  access_entries = {
    github_deploy = {
      principal_arn = aws_iam_role.github_deploy.arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }
}

resource "aws_ecr_repository" "web" {
  name                 = "culprit-web"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# --- Keyless CI -> AWS: GitHub Actions OIDC -----------------------------------
# deploy.yml assumes this role via OIDC; no long-lived AWS keys ever live in
# repo secrets. Trust is pinned to this repository.

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.cluster_name}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

resource "aws_iam_role_policy_attachment" "github_ecr" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}

data "aws_iam_policy_document" "github_eks" {
  statement {
    actions   = ["eks:DescribeCluster"]
    resources = [module.eks.cluster_arn]
  }
}

resource "aws_iam_role_policy" "github_eks" {
  name   = "eks-describe"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_eks.json
}

# --- Outputs deploy.yml and humans need --------------------------------------

output "cluster_name" {
  value = module.eks.cluster_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.web.repository_url
}

output "github_deploy_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable for deploy.yml"
  value       = aws_iam_role.github_deploy.arn
}
