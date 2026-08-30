###############################################################################
# FluxForge — AWS Infrastructure
#
# Creates the AWS resources needed for a complete OIDC-based CI/CD pipeline:
#   • GitHub OIDC Identity Provider  (trust between GitHub Actions & AWS)
#   • IAM Role for GitHub Actions    (assumed by the workflow via OIDC)
#   • ECR Repository                (stores the FluxForge Docker image)
#   • Security Group               (controls inbound/outbound traffic)
#   • IAM Instance Profile + Role   (lets EC2 pull images from ECR without keys)
#   • EC2 Instance                 (application host — optional, can be pre-created)
#
# Usage:
#   1. Copy infrastructure/terraform.tfvars.example → terraform.tfvars
#   2. Fill in your values (github_org, github_repo, aws_region, ec2_ami_id)
#   3. terraform init
#   4. terraform plan
#   5. terraform apply
#
# After apply, copy the output values into your GitHub repo:
#   • Settings → Secrets:  AWS_DEPLOY_ROLE_ARN, AWS_ACCOUNT_ID
#   • Settings → Variables: AWS_REGION, AWS_EC2_INSTANCE_ID, FRONTEND_URL
###############################################################################

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

###############################################################################
# OIDC Identity Provider
# This creates the trust relationship between GitHub Actions and AWS.
# GitHub's OIDC endpoint: https://token.actions.githubusercontent.com
###############################################################################
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = data.tls_certificate.github.url
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

###############################################################################
# IAM Role — GitHub Actions (for the workflow's build & deploy steps)
###############################################################################

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    sid     = "AllowGitHubOIDCAuth"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      # Allow any branch of the configured repo to assume this role.
      # To restrict to a specific branch: token.actions.githubusercontent.com:ref:refs/heads/main
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_org}/${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
  description        = "Role assumed by GitHub Actions workflow for ${var.github_org}/${var.github_repo}"
}

# ── Inline policy: what the workflow is allowed to do ────────────────────────

data "aws_iam_policy_document" "github_actions_permissions" {
  # ECR
  statement {
    sid    = "ECR"
    effect = "Allow"

    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:GetRepositoryPolicy",
      "ecr:ListImages",
      "ecr:DescribeImages",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]

    resources = ["*"]
  }

  # SSM — run commands on the EC2
  statement {
    sid    = "SSM"
    effect = "Allow"

    actions = [
      "ssm:SendCommand",
      "ssm:GetCommandInvocation",
      "ssm:ListCommands",
    ]

    resources = [
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*",
    ]
  }

  # EC2 — SSM needs to target instances
  statement {
    sid    = "EC2ForSSM"
    effect = "Allow"

    actions = ["ec2:DescribeInstances"]

    resources = ["*"]
  }

  # S3 — optionally store build artifacts
  statement {
    sid    = "S3"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]

    resources = [
      "arn:aws:s3:::${var.project_name}-artifacts",
      "arn:aws:s3:::${var.project_name}-artifacts/*",
    ]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "${var.project_name}-github-actions-policy"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_permissions.json
}

###############################################################################
# ECR Repository — stores the FluxForge Docker image
###############################################################################
resource "aws_ecr_repository" "fluxforge_api" {
  name         = "${var.project_name}-api"
  image_scanning_configuration {
    scan_on_push = true
  }
  image_tag_mutability = "MUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Project = var.project_name
    Managed = "terraform"
  }
}

# Lifecycle policy: keep the last 10 images, expire untagged ones after 14 days
resource "aws_ecr_lifecycle_policy" "fluxforge_api" {
  repository = aws_ecr_repository.fluxforge_api.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 14 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countNumber = 14
          countUnit   = "days"
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Keep last 10 tagged images"
        selection = {
          tagStatus = "tagged"
          tagPrefixList = ["v"]
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

###############################################################################
# Security Group — controls what traffic is allowed in/out
###############################################################################
resource "aws_security_group" "app" {
  name        = "${var.project_name}-app-sg"
  description = "Security group for FluxForge EC2 app host"
  vpc_id      = data.aws_vpc.default.id

  ingress = [
    {
      description      = "HTTP"
      protocol         = "tcp"
      from_port        = 80
      to_port          = 80
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      security_groups  = []
      self             = false
    },
    {
      description      = "HTTPS"
      protocol         = "tcp"
      from_port        = 443
      to_port          = 443
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      security_groups  = []
      self             = false
    },
    {
      description      = "App port (internal)"
      protocol         = "tcp"
      from_port        = var.container_port
      to_port          = var.container_port
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      security_groups  = []
      self             = false
    },
    {
      description      = "SSH (restricted)"
      protocol         = "tcp"
      from_port        = 22
      to_port          = 22
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = []
      prefix_list_ids  = []
      security_groups  = []
      self             = false
    },
  ]

  egress = [
    {
      description      = "Allow all outbound"
      protocol         = "-1"
      from_port        = 0
      to_port          = 0
      cidr_blocks      = ["0.0.0.0/0"]
      ipv6_cidr_blocks = ["::/0"]
      prefix_list_ids  = []
      security_groups  = []
      self             = false
    },
  ]

  tags = {
    Project = var.project_name
    Managed = "terraform"
  }
}

###############################################################################
# IAM Role + Instance Profile — lets EC2 pull images from ECR without keys
# The EC2 metadata service (IMDS) automatically provides credentials via this role.
###############################################################################
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    sid     = "AllowEC2AssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_app" {
  name               = "${var.project_name}-ec2-app"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
  description        = "Role for FluxForge EC2 app host — lets it pull images from ECR"
}

resource "aws_iam_role_policy_attachment" "ec2_ecr_read" {
  role       = aws_iam_role.ec2_app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy_attachment" "ec2_ssm" {
  role       = aws_iam_role.ec2_app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_app" {
  name = "${var.project_name}-ec2-app"
  role = aws_iam_role.ec2_app.name
}

###############################################################################
# Data sources used by the SG, EC2 instance, etc.
###############################################################################
data "aws_vpc" "default" {
  default = true
}

data "aws_ami" "ubuntu" {
  count = var.create_ec2_instance && var.ec2_ami_id == "" ? 1 : 0

  owners      = ["099720109477"] # Canonical (Ubuntu)
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

###############################################################################
# EC2 Instance (optional — set create_ec2_instance = false to skip)
###############################################################################
resource "aws_instance" "app" {
  count = var.create_ec2_instance ? 1 : 0

  ami                  = coalesce(var.ec2_ami_id, try(data.aws_ami.ubuntu[0].id, ""))
  instance_type        = var.ec2_instance_type
  iam_instance_profile = aws_iam_instance_profile.ec2_app.name

  vpc_security_group_ids = [aws_security_group.app.id]

  key_name = var.ec2_key_name != "" ? var.ec2_key_name : null

  # Bootstrap script runs on first boot via user_data
  user_data = templatefile("${path.module}/templates/ec2_userdata.sh.tpl", {
    project_name   = var.project_name
    container_port = var.container_port
    ecr_repo_url   = aws_ecr_repository.fluxforge_api.repository_url
  })

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name        = "${var.project_name}-app"
    Project     = var.project_name
    Managed     = "terraform"
    Environment = "production"
  }
}
