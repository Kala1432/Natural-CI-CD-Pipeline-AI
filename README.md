# FluxForge — AI-powered CI/CD Pipeline Generator
http://13.60.87.124:3001/register
FluxForge is a production-ready, full-stack AI-powered DevOps automation platform. Built with Python, Flask, React.js, PostgreSQL, Redis, AWS, OpenAI, Docker, and GitHub Actions, it automates the repository intelligence, deployment configurations, and ML-assisted monitoring.

> *Forge your pipelines with AI.*

## Features
- **Secure Authentication & RBAC:** JWT authentication (HttpOnly cookies), GitHub OAuth, Argon2 secure hashing, and granular Role-Based Access Controls.
- **Repository Intelligence:** Automatic workflow generation for Python, Flask, Docker, Node.js, Go and AI projects.
- **AI Recommendation Engine:** Generates secure and sound `Dockerfile` and `ci.yml` configurations with user-in-the-loop review mechanism.
- **Automated Deployment:** Deploy to AWS EC2 natively via GitHub Actions OIDC + SSM.
- **ML Anomaly Detection:** Real-time metrics monitoring (CPU/Memory) with simulated automated rollbacks.
- **Admin Dashboard:** Platform-wide analytics tracking active projects, workflow generations, and deployments.
- **Real-time Metrics:** Deployment health-checks and active incident log tracking.

## Project Structure
- `backend/` - Flask REST API, database models, AI and deployment services
- `frontend/` - React frontend with Tailwind CSS and dashboard components
- `docker-compose.yml` - Local development stack with PostgreSQL, Redis, MongoDB, Celery worker
- `infrastructure/` - Terraform code for AWS (OIDC, ECR, IAM, EC2, Security Group)
- `.github/workflows/deploy-aws.yml` - GitHub Actions pipeline (Test → Build → ECR → SSM)
- `scripts/` - EC2 bootstrap, production entrypoint, and helper scripts

## Setup (Local Development)
1. Copy `.env.example` to `.env` and fill in secrets.
2. Start Docker services:
   ```bash
   docker compose up --build
   ```
3. In another terminal, initialize the database:
   ```bash
   docker compose exec backend flask db upgrade
   ```
4. Access the frontend at `http://localhost:3001` and API at `http://localhost:5001/api/health`.

## Development
- Backend: `cd backend && pip install -r requirements.txt`
- Frontend: `cd frontend && npm install`

---

## One-time AWS Production Setup (OIDC + ECR + EC2)

The deployment pipeline uses **GitHub OIDC** for authentication (no long-lived AWS keys) and **SSM Run Command** to deploy to a pre-provisioned EC2 instance. The pipeline goes:

```
git push main
  → GitHub Actions (OIDC assumes AWS role)
    → Test (pytest + frontend build)
    → Build & push Docker image to ECR
    → SSM Run Command → EC2
       → docker pull (using instance profile IAM role)
       → docker stop old container
       → docker run new container
```

### Step 1: Provision AWS infrastructure with Terraform

```bash
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set github_org, github_repo, aws_region, ec2_instance_type
terraform init
terraform plan
terraform apply
```

This creates:
- ✅ GitHub OIDC Identity Provider
- ✅ IAM Role `fluxforge-github-actions` (assumable from your repo)
- ✅ ECR Repository `fluxforge-api`
- ✅ Security Group (ports 80, 443, 5000, 22)
- ✅ IAM Instance Profile `fluxforge-ec2-app` (lets EC2 pull from ECR)
- ✅ EC2 Instance (Ubuntu 22.04, t3.small by default) with SSM agent + Docker pre-installed

Capture the outputs:
```bash
terraform output
# You will need:
#   - github_actions_role_arn  → AWS_DEPLOY_ROLE_ARN secret
#   - ec2_instance_id          → AWS_EC2_INSTANCE_ID variable
#   - aws_account_id           → AWS_ACCOUNT_ID secret
#   - ecr_repository_url       → (informational)
```

### Step 2: Configure GitHub repository

In **Settings → Secrets and variables → Actions**, add the following:

**Secrets (one-time):**
| Name | Example value |
|------|---------------|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::123456789012:role/fluxforge-github-actions` |
| `AWS_ACCOUNT_ID` | `123456789012` |
| `DATABASE_URL` | `postgresql://user:pass@your-rds-host:5432/pipeline_sh` |
| `REDIS_URL` | `redis://your-redis-host:6379/0` |
| `JWT_SECRET_KEY` | (random 64-char string) |
| `SECRET_KEY` | (random 64-char string) |
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/db` |
| `GEMINI_API_KEY` | your Gemini API key |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `465` |
| `SMTP_USERNAME` | `your-sender@gmail.com` |
| `SMTP_APP_PASSWORD` | (Google App Password) |
| `EMAIL_FROM` | `your-sender@gmail.com` |

**Variables:**
| Name | Example value |
|------|---------------|
| `AWS_REGION` | `ap-south-1` |
| `AWS_EC2_INSTANCE_ID` | `i-0123456789abcdef0` |
| `FRONTEND_URL` | `https://api.fluxforge.ai` |

### Step 3: Bootstrap the EC2 instance (one-time)

If you used Terraform to create the EC2, the bootstrap script already ran on first boot (via `user_data`). Verify by SSHing in (or via Session Manager):
```bash
aws ssm start-session --target i-0123456789abcdef0
sudo /var/log/fluxforge-bootstrap.log
docker --version
```

If you provisioned the EC2 manually, run the bootstrap script:
```bash
scp -i your-key.pem scripts/ec2_bootstrap.sh ubuntu@<ec2-ip>:/tmp/
ssh -i your-key.pem ubuntu@<ec2-ip> "bash /tmp/ec2_bootstrap.sh"
```

Then attach the IAM instance profile (if not done by Terraform):
- AWS Console → EC2 → Instances → Select your instance
- Actions → Security → Modify IAM role → Choose `fluxforge-ec2-app`

### Step 4: Deploy!

```bash
git push origin main
```

This triggers `.github/workflows/deploy-aws.yml`:
1. **Test** — pytest + frontend build
2. **Build & Push** — multi-stage Docker build pushed to ECR
3. **Deploy** — SSM Run Command to your EC2, which pulls the new image and restarts the container

You can monitor the deployment:
- GitHub: Actions tab → Select the workflow run
- AWS: Systems Manager → Run Command → Execution history
- EC2: `docker ps` (via Session Manager)

### Manual deploy

You can also trigger a manual deployment from the GitHub Actions UI:
1. Go to Actions → "FluxForge — Build & Deploy to AWS"
2. Click "Run workflow"
3. Choose environment (production / staging)
4. Click "Run workflow"

## Notes
This starter platform includes AI-driven helpers and deployment scaffolding. The OIDC pipeline removes the need to store AWS credentials in GitHub Secrets — the workflow's temporary credentials automatically expire after the job completes.
