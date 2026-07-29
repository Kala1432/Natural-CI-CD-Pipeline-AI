# AWS continuous deployment

## Low-cost EC2 deployment

For demos, `deploy/aws/ec2-low-cost.yml` creates one EC2 instance and runs the
application, PostgreSQL, and Redis as local Docker containers. GitHub Actions
deploys updates through AWS Systems Manager with short-lived OIDC credentials,
so no SSH key or permanent AWS access key is required.

The stack outputs the public URL, EC2 instance ID, and GitHub deployment role.
Set the instance ID as repository variable `AWS_EC2_INSTANCE_ID`, the role ARN
as repository secret `AWS_DEPLOY_ROLE_ARN`, and `ap-south-1` as repository
variable `AWS_REGION`.

Normal AWS usage charges still apply. Delete the stack when it is not needed.

## Scalable ECS deployment

Pipeline.sh uses one production container deployed to Amazon ECS Fargate. React is
built into the image and served by Flask through Gunicorn. PostgreSQL, Redis, and
secrets remain outside the container.

## Required AWS resources

- Amazon ECR repository: `pipeline-sh`
- ECS Fargate cluster and service: `pipeline-sh`
- Application Load Balancer targeting container port `5000`
- RDS PostgreSQL database
- ElastiCache Redis cluster
- CloudWatch log group: `/ecs/pipeline-sh`
- ECS execution role with ECR, CloudWatch, and SSM parameter permissions
- ECS task role: `pipeline-sh-task-role`
- GitHub OIDC provider and deploy role restricted to this repository and `main`

The load balancer health check path is `/api/health`.

## Parameter Store values

Create SecureString parameters with these names:

```text
/pipeline-sh/production/DATABASE_URL
/pipeline-sh/production/REDIS_URL
/pipeline-sh/production/SECRET_KEY
/pipeline-sh/production/JWT_SECRET_KEY
/pipeline-sh/production/GITHUB_CLIENT_ID
/pipeline-sh/production/GITHUB_CLIENT_SECRET
/pipeline-sh/production/SMTP_USERNAME
/pipeline-sh/production/SMTP_APP_PASSWORD
/pipeline-sh/production/EMAIL_FROM
/pipeline-sh/production/FRONTEND_URL
/pipeline-sh/production/BACKEND_URL
```

`FRONTEND_URL` and `BACKEND_URL` should both use the public HTTPS origin when the
frontend and API are served from the same container.

## GitHub repository configuration

Create a protected `production` environment and add:

- Secret `AWS_DEPLOY_ROLE_ARN`
- Variable `AWS_REGION` (defaults to `ap-south-1`)
- Variable `ECR_REPOSITORY` (defaults to `pipeline-sh`)
- Variable `ECS_CLUSTER` (defaults to `pipeline-sh`)
- Variable `ECS_SERVICE` (defaults to `pipeline-sh`)

The AWS role trust policy must restrict GitHub OIDC access to this repository and
the production environment or `main` branch.

## Deployment behavior

Every push to `main`:

1. Runs backend tests.
2. Builds the React frontend.
3. Assumes the AWS role through GitHub OIDC.
4. Builds and pushes an image tagged with the commit SHA.
5. Registers a new ECS task definition revision.
6. Updates the ECS service and waits for stability.

The container runs `flask db upgrade` before Gunicorn starts. Alembic migrations
must therefore remain backward-compatible during rolling deployments.

## OAuth production change

Update the GitHub OAuth App after the public domain is ready:

- Homepage URL: `https://your-domain`
- Callback URL: `https://your-domain/api/auth/github/callback`

Do not remove the localhost callback until local development uses a separate
GitHub OAuth App.
