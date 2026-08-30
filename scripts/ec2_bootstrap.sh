#!/bin/bash
###############################################################################
# FluxForge — EC2 Bootstrap Script
#
# Run this script on a pre-provisioned EC2 instance (via SSH or SSM Session
# Manager) to install Docker, AWS CLI, and prepare the host for deployments.
#
# Usage:
#   chmod +x scripts/ec2_bootstrap.sh
#   ./scripts/ec2_bootstrap.sh
#
# After this script runs, the instance will be ready to receive deployments
# via the GitHub Actions workflow (SSM Run Command).
###############################################################################

set -e

echo "============================================"
echo " FluxForge — EC2 Bootstrap"
echo "============================================"
echo "Starting at $(date -Iseconds)"
echo ""

# ── Step 1: System update ──────────────────────────────────────────────────
echo "[1/6] Updating system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
echo "✓ System updated"

# ── Step 2: Install core utilities ─────────────────────────────────────────
echo "[2/6] Installing Docker, unzip, curl..."
apt-get install -y \
  docker.io \
  docker-compose-v2 \
  unzip \
  curl \
  ca-certificates \
  gnupg \
  lsb-release
echo "✓ Core utilities installed"

# ── Step 3: Docker daemon ───────────────────────────────────────────────────
echo "[3/6] Configuring Docker daemon..."
systemctl enable docker
systemctl start docker

# Allow ubuntu user to run docker
if id -u ubuntu &>/dev/null; then
  usermod -aG docker ubuntu
  echo "✓ Added ubuntu user to docker group"
else
  echo "⚠ ubuntu user not found — skipping docker group (may be a different OS)"
fi

# Verify
docker --version
echo "✓ Docker is running"

# ── Step 4: AWS CLI v2 ────────────────────────────────────────────────────
echo "[4/6] Installing AWS CLI v2..."
if ! command -v aws &>/dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp/awscliv2
  /tmp/awscliv2/aws/install --update
  rm -rf /tmp/awscliv2 /tmp/awscliv2.zip
fi
aws --version
echo "✓ AWS CLI installed"

# ── Step 5: Verify SSM agent ────────────────────────────────────────────────
echo "[5/6] Checking SSM agent..."
if systemctl is-active --quiet amazon-ssm-agent 2>/dev/null || \
   systemctl is-active --quiet snap.amazon-ssm-agent.amazon-ssm-agent 2>/dev/null; then
  echo "✓ SSM agent is running"
elif command -v amazon-ssm-agent &>/dev/null; then
  echo "SSM agent binary found but not running — attempting to start..."
  systemctl enable --now amazon-ssm-agent || echo "⚠ Could not start SSM agent automatically"
else
  echo "⚠ SSM agent not detected — install it from:"
  echo "  https://docs.aws.amazon.com/systems-manager/latest/userguide/ssm-agent.html"
fi

# ── Step 6: Create app directory & Docker network ──────────────────────────
echo "[6/6] Creating application directories..."
mkdir -p /opt/fluxforge
chown -R ubuntu:docker /opt/fluxforge 2>/dev/null || true
docker network create fluxforge-net 2>/dev/null || true
echo "✓ Directories and Docker network created"

echo ""
echo "============================================"
echo " Bootstrap complete at $(date -Iseconds)"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Attach the IAM instance profile '${IAM_INSTANCE_PROFILE:-fluxforge-ec2-app}' to this EC2"
echo "     (AWS Console → EC2 → Instances → Actions → Security → Modify IAM role)"
echo "  2. Ensure the security group allows port 5000 (app), 80 (HTTP), 443 (HTTPS)"
echo "  3. Push to main branch — GitHub Actions will deploy via SSM"
echo ""
echo "To test ECR access:"
echo "  aws ecr get-login-password --region \${AWS_REGION:-ap-south-1} | \\"
echo "    docker login --username AWS --password-stdin \${AWS_ACCOUNT_ID}.dkr.ecr.\${AWS_REGION:-ap-south-1}.amazonaws.com"
