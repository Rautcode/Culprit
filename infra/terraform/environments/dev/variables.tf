variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-south-1"
}

variable "cluster_name" {
  description = "EKS cluster name; prefixes shared resources"
  type        = string
  default     = "culprit-dev"
}

variable "github_repo" {
  description = "owner/repo allowed to assume the OIDC deploy role"
  type        = string
  default     = "Rautcode/Culprit"
}
