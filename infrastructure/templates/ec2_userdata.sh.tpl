#!/bin/bash
###############################################################################
# FluxForge — EC2 bootstrap script (runs on first boot via user_data)
#
# Installs Docker, SSM agent (already pre-installed on the official Ubuntu AMI),
# and prepares the host for deployments via SSM.
#
# Variables injected by Terraform (templatefile):
#   • project_name    = e.g. fluxforge
#   • container_port  = port the app container will expose
#   • ecr_repo_url    = e.g. 123456789012.dkr.ecr.ap-south-1.amazonaws.com/fluxforge-api
###############################################################################

set -e
exec > >(tee /var/log/fluxforge-bootstrap.log) 2>&1

echo "=== FluxForge EC2 bootstrap starting at $(date) ==="
echo "Project: ${project_name}"
echo "Container port: ${container_port}"
echo "ECR repository: ${ecr_repo_url}"

# ── Step 1: System update ────────────────────────────────────────────────────
echo "[1/5] Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# ── Step 2: Install Docker ───────────────────────────────────────────────────
echo "[2/5] Installing Docker..."
apt-get install -y docker.io

# Enable & start Docker
systemctl enable docker
systemctl start docker

# Allow the ubuntu user to run docker without sudo
usermod -aG docker ubuntu

# Verify Docker installation
docker --version
echo "Docker installed successfully."

# ── Step 3: Install AWS CLI v2 ───────────────────────────────────────────────
echo "[3/5] Installing AWS CLI v2..."
if ! command -v aws &> /dev/null; then
  apt-get install -y unzip
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp/awscliv2
  /tmp/awscliv2/aws/install
  rm -rf /tmp/awscliv2 /tmp/awscliv2.zip
fi
aws --version
echo "AWS CLI installed successfully."

# ── Step 4: Test ECR access (uses the instance profile role) ─────────────────
echo "[4/5] Testing ECR access..."
# The instance profile role has AmazonEC2ContainerRegistryReadOnly, so we can
# authenticate docker to the ECR registry without long-lived credentials.
REGION=$(echo "${ecr_repo_url}" | cut -d. -f4)
ACCOUNT_ID=$(echo "${ecr_repo_url}" | cut -d. -f1)

if aws ecr get-login-password --region "$REGION" 2>/dev/null | \
   docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com" 2>/dev/null; then
  echo "✓ ECR login successful — instance can pull images"
else
  echo "⚠ ECR login test failed (this is OK on first boot; the workflow will retry)"
fi

# ── Step 5: Create deploy directory ──────────────────────────────────────────
echo "[5/5] Creating deploy directory..."
mkdir -p /opt/fluxforge
chown -R ubuntu:ubuntu /opt/fluxforge

# Create a docker network for the app
docker network create fluxforge-net || true

echo "=== FluxForge EC2 bootstrap complete at $(date) ==="
echo "Next: GitHub Actions will deploy the application via SSM."
