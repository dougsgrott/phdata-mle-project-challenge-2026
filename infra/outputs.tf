output "ecr_repository_url" {
  description = "Where CI and manual pushes send the API image"
  value       = aws_ecr_repository.api.repository_url
}

output "api_url" {
  description = "Stage URL for reviewers, smoke tests and the UI"
  value       = aws_api_gateway_stage.api.invoke_url
}

output "api_key_parameter" {
  description = "SSM parameter holding the API key"
  value       = aws_ssm_parameter.api_key.name
}