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