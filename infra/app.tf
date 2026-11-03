# Container registry for the API image; CI pushes one tag per git SHA
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "IMMUTABLE" # a SHA tag can never point at a different image
  force_delete         = true        # lets terraform destroy remove it with images inside

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep the last 5 images: the rollback window, and storage stays at cents
resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# The image the function is created with: the newest one in ECR (pushed in step 4).
# After creation, CI owns the image (ignore_changes below).
data "aws_ecr_image" "bootstrap" {
  repository_name = aws_ecr_repository.api.name
  most_recent     = true
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.project}-api"
  retention_in_days = 14
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-api-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# The function may only write to its own log group
resource "aws_iam_role_policy" "lambda_logs" {
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "${aws_cloudwatch_log_group.api.arn}:*"
    }]
  })
}

resource "aws_lambda_function" "api" {
  function_name = "${var.project}-api"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.api.repository_url}@${data.aws_ecr_image.bootstrap.image_digest}"
  architectures = ["x86_64"]
  memory_size   = 2048
  timeout       = 29 # API Gateway gives up at 29 s anyway

  environment {
    variables = {
      # The stage name is in the public URL; this lets /docs find /v1/openapi.json
      UVICORN_ROOT_PATH = "/${local.stage_name}"
      # Startup takes about 9 s on Lambda (pandas and scikit-learn imports); without this,
      # anything over 10 s fails the request instead of just slowing it down
      AWS_LWA_ASYNC_INIT = "true"
    }
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy.lambda_logs]

  lifecycle {
    ignore_changes = [image_uri] # deploys go through CI, not Terraform
  }
}

# Copy of the gateway's key, for CI and for you
resource "aws_ssm_parameter" "api_key" {
  name  = "/${var.project}/api-key"
  type  = "SecureString"
  value = aws_api_gateway_api_key.reviewers.value
}