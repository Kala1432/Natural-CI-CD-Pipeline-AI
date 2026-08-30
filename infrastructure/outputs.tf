###############################################################################
# FluxForge — Terraform Outputs
#
# Copy these values into your GitHub repository settings after running
# `terraform apply`.
#
# GitHub Secrets (Settings → Secrets and variables → Actions):
#   • AWS_DEPLOY_ROLE_ARN  = output value below
#   • AWS_ACCOUNT_ID        = output value below (or use data.aws_caller_identity.current.account_id)
#   • DATABASE_URL          = your production PostgreSQL connection string
#   • REDIS_URL             = your production Redis URL
#   • JWT_SECRET_KEY        = random 64-char secret
#   • SECRET_KEY            = random 64-char secret
#   • MONGODB_URI           = your MongoDB Atlas connection string
#   • SMTP_*                = your email credentials
#   • GEMINI_API_KEY        = your Gemini API key
#
# GitHub Variables (Settings → Secrets and variables → Actions → Variables):
#   • AWS_REGION            = output value below
#   • AWS_EC2_INSTANCE_ID   = EC2 instance ID (if pre-provisioned, not created by Terraform)
#   • FRONTEND_URL          = your public domain, e.g. https://api.fluxforge.ai
###############################################################################

output "github_actions_role_arn" {
  description = "ARN of the IAM role for GitHub Actions. Add this as AWS_DEPLOY_ROLE_ARN in GitHub Secrets."
  value       = aws_iam_role.github_actions.arn
}

output "github_actions_role_name" {
  description = "Name of the IAM role for GitHub Actions."
  value       = aws_iam_role.github_actions.name
}

output "ecr_repository_url" {
  description = "URL of the ECR repository. Use this as the image prefix in docker build/push commands."
  value       = aws_ecr_repository.fluxforge_api.repository_url
}

output "ecr_repository_name" {
  description = "Name of the ECR repository."
  value       = aws_ecr_repository.fluxforge_api.name
}

output "security_group_id" {
  description = "ID of the application security group."
  value       = aws_security_group.app.id
}

output "ec2_instance_profile" {
  description = "Name of the IAM instance profile for the EC2 app host. Attach this to any EC2 you provision manually."
  value       = aws_iam_instance_profile.ec2_app.name
}

output "ec2_instance_id" {
  description = "ID of the EC2 instance created by Terraform. If you set create_ec2_instance=false, this will be empty — use your own instance ID instead."
  value       = length(aws_instance.app) > 0 ? aws_instance.app[0].id : ""
}

output "ec2_public_ip" {
  description = "Public IPv4 address of the EC2 instance."
  value       = length(aws_instance.app) > 0 ? aws_instance.app[0].public_ip : ""
}

output "ec2_private_ip" {
  description = "Private IPv4 address of the EC2 instance."
  value       = length(aws_instance.app) > 0 ? aws_instance.app[0].private_ip : ""
}

output "aws_account_id" {
  description = "Your AWS account ID. Add this as AWS_ACCOUNT_ID in GitHub Secrets."
  value       = data.aws_caller_identity.current.account_id
}

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC provider created by Terraform."
  value       = aws_iam_openid_connect_provider.github.arn
}
