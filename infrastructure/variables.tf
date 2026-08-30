###############################################################################
# FluxForge — AWS infrastructure variables
#
# Configure these to match your AWS account and GitHub repository. All
# variables are passed via `terraform.tfvars` (git-ignored) or `-var` flags.
###############################################################################

variable "aws_region" {
  description = "AWS region where all resources will be created."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Short project identifier used as a prefix for resource names."
  type        = string
  default     = "fluxforge"
}

variable "github_org" {
  description = "GitHub organization or username that owns the repository. e.g. 'prabhu' or 'fluxforge-ai'."
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name. e.g. 'Natural-CI-CD-Pipeline-AI'."
  type        = string
  default     = "Natural-CI-CD-Pipeline-AI"
}

variable "github_branch" {
  description = "Branch whose workflow runs are allowed to assume the deploy role. Set to '*' to allow all branches."
  type        = string
  default     = "main"
}

variable "ec2_instance_type" {
  description = "EC2 instance type for the application host."
  type        = string
  default     = "t3.small"
}

variable "ec2_ami_id" {
  description = "AMI ID for the EC2 instance. Use a recent Ubuntu 22.04 LTS image for your region."
  type        = string
  default     = ""
}

variable "ec2_key_name" {
  description = "Name of an existing EC2 key pair to allow SSH access. Leave empty to skip SSH key."
  type        = string
  default     = ""
}

variable "create_ec2_instance" {
  description = "If true, terraform also creates the EC2 instance. If false, only IAM/ECR/SG are created and you manage the instance separately."
  type        = bool
  default     = true
}

variable "container_port" {
  description = "Port the application container listens on inside the EC2 instance."
  type        = number
  default     = 5000
}
