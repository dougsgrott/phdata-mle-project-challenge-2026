locals {
  stage_name = "v1"
  # Routes anyone can open without a key
  open_paths = toset(["health", "docs", "openapi.json"])
}

resource "aws_api_gateway_rest_api" "api" {
  name = "${var.project}-api"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# Every other path (/predict, /predict/batch) requires the key
resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = "{proxy+}"
}

resource "aws_api_gateway_method" "proxy" {
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = aws_api_gateway_resource.proxy.id
  http_method      = "ANY"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_integration" "proxy" {
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.api.invoke_arn
}

resource "aws_api_gateway_resource" "open" {
  for_each    = local.open_paths
  rest_api_id = aws_api_gateway_rest_api.api.id
  parent_id   = aws_api_gateway_rest_api.api.root_resource_id
  path_part   = each.key
}

resource "aws_api_gateway_method" "open" {
  for_each         = aws_api_gateway_resource.open
  rest_api_id      = aws_api_gateway_rest_api.api.id
  resource_id      = each.value.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_integration" "open" {
  for_each                = aws_api_gateway_method.open
  rest_api_id             = aws_api_gateway_rest_api.api.id
  resource_id             = each.value.resource_id
  http_method             = each.value.http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = aws_lambda_function.api.invoke_arn
}

# Without the triggers hash, route changes would never go live
resource "aws_api_gateway_deployment" "api" {
  rest_api_id = aws_api_gateway_rest_api.api.id

  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_method.proxy,
      aws_api_gateway_integration.proxy,
      aws_api_gateway_method.open,
      aws_api_gateway_integration.open,
    ]))
  }

  depends_on = [aws_api_gateway_integration.proxy, aws_api_gateway_integration.open]

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "api" {
  rest_api_id   = aws_api_gateway_rest_api.api.id
  deployment_id = aws_api_gateway_deployment.api.id
  stage_name    = local.stage_name
}

# Hard cap on load and cost: 10 req/s, burst 20, 5,000 requests a day
resource "aws_api_gateway_usage_plan" "reviewers" {
  name = "${var.project}-reviewers"

  api_stages {
    api_id = aws_api_gateway_rest_api.api.id
    stage  = aws_api_gateway_stage.api.stage_name
  }

  throttle_settings {
    rate_limit  = 10
    burst_limit = 20
  }

  quota_settings {
    limit  = 5000
    period = "DAY"
  }
}

resource "aws_api_gateway_api_key" "reviewers" {
  name = "${var.project}-reviewers" # AWS generates the value
}

resource "aws_api_gateway_usage_plan_key" "reviewers" {
  key_id        = aws_api_gateway_api_key.reviewers.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.reviewers.id
}

# Only this API may invoke the function: there is no other way in
resource "aws_lambda_permission" "gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.api.execution_arn}/*/*"
}