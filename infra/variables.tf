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
