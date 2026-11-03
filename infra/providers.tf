terraform {
  required_version = ">= 1.10" # S3 native locking (use_lockfile)

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.35" # 6.35 adds aws_sagemaker_mlflow_app (P6)
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # The bucket is created once by hand (roadmap step 3).
  # Backend blocks can't read variables, so the region is repeated here.
  backend "s3" {
    bucket       = "sound-realty-tfstate-866217459284"
    key          = "sound-realty/terraform.tfstate"
    region       = "us-west-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region

  # Every resource carries these, so Cost Explorer and teardown can find them
  default_tags {
    tags = {
      project    = var.project
      managed_by = "terraform"
      expires_on = var.expires_on
    }
  }
}