variable "project" {
  description = "Prefix for resource names and the project tag"
  type        = string
  default     = "sound-realty"
}

variable "region" {
  description = "AWS region for every resource (D20)"
  type        = string
  default     = "us-west-2"
}

variable "alert_email" {
  description = "Where alarm and budget emails go"
  type        = string
}

variable "github_repository" {
  description = "Repository allowed to deploy, as GitHub writes it in the OIDC subject: owner@ownerId/name@repoId"
  type        = string
}