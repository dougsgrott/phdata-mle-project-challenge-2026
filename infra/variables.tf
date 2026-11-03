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

variable "expires_on" {
  description = "Date (YYYY-MM-DD) when everything is destroyed; tagged on every resource"
  type        = string

  validation {
    condition     = can(regex("^\\d{4}-\\d{2}-\\d{2}$", var.expires_on))
    error_message = "expires_on must be a date in YYYY-MM-DD form."
  }
}