output "ecr_repository_url" {
  description = "Where CI and manual pushes send the API image"
  value       = aws_ecr_repository.api.repository_url
}