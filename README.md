# Pipeline.sh

Pipeline.sh is a full-stack AI-powered DevOps automation platform built with Python, Flask, React.js, TensorFlow, PostgreSQL, Redis, AWS, OpenAI, Docker, and GitHub Actions.

## Features
- JWT authentication and GitHub OAuth
- GitHub repository integration and webhook handling
- Automatic workflow generation for Python, Flask, Docker, and AI projects
- AI/NLP-based error detection and debugging suggestions
- Real-time analytics dashboard and pipeline monitoring
- AWS EC2 deployment automation and S3 artifact integration
- Redis caching and PostgreSQL persistence
- Docker Compose development environment

## Project Structure
- `backend/` - Flask REST API, database models, AI and deployment services
- `frontend/` - React frontend with Tailwind CSS and dashboard components
- `docker-compose.yml` - Local development stack with PostgreSQL and Redis
- `.github/workflows/ci-cd.yml` - GitHub Actions pipeline template
- `scripts/` - AWS deployment automation scripts
- `nginx/` - Nginx reverse proxy configuration

## Setup
1. Copy `.env.example` to `.env` and fill in secrets.
2. Start Docker services:
   ```bash
   docker compose up --build
   ```
3. In another terminal, initialize the database:
   ```bash
   docker compose exec backend flask db upgrade
   ```
4. Access the frontend at `http://localhost:3000` and API at `http://localhost:5000/api/health`.

## Development
- Backend: `cd backend && pip install -r requirements.txt`
- Frontend: `cd frontend && npm install`

## Deployment
- Use `scripts/deploy_ec2.sh` to provision an EC2 instance and deploy the Docker image.
- Configure AWS credentials in your environment before running deployment scripts.

## Notes
This starter platform includes AI-driven helpers and deployment scaffolding. Extend the service layer with production-grade GitHub webhook validation, strong RBAC, encrypted secrets storage, and full AWS infrastructure automation.
