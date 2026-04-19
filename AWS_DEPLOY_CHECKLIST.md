# AWS App Runner Deployment Checklist for LLM Gateway

This checklist will guide you through deploying your FastAPI LLM Gateway (with UI, Redis, and Prometheus) to AWS App Runner using best practices from your repo.

---

## 1. Prerequisites

- [ ] AWS account with billing enabled
- [ ] AWS CLI installed and configured (`aws configure`)
- [ ] Docker Desktop running (with buildx enabled)
- [ ] Upstash or Redis Cloud account for managed Redis
- [ ] All secrets (API keys) ready

## 2. Prepare Environment Variables

- [ ] Copy `env.example` to `.env` and fill in real values
- [ ] (For AWS) Store secrets in AWS Secrets Manager
- [ ] Set `REDIS_URL` to your Upstash/Redis Cloud endpoint

## 3. Build and Push Docker Image

- [ ] Authenticate Docker to AWS ECR:
  ```bash
  aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com
  ```
- [ ] Create ECR repository (if not exists):
  ```bash
  aws ecr create-repository --repository-name llm-gateway
  ```
- [ ] Build multi-arch image for AWS:
  ```bash
  docker buildx build --platform linux/amd64 -t llm-gateway:latest .
  docker tag llm-gateway:latest <aws_account_id>.dkr.ecr.<region>.amazonaws.com/llm-gateway:latest
  docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/llm-gateway:latest
  ```

## 4. Deploy to AWS App Runner

- [ ] Go to AWS App Runner console
- [ ] Create a new service from ECR image
- [ ] Set port to `8000` (FastAPI default)
- [ ] Add environment variables:
  - `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `REDIS_URL`, etc.
  - (Recommended) Use AWS Secrets Manager integration
- [ ] Set resources (1 vCPU, 2GB RAM is sufficient)
- [ ] Deploy and wait for health checks to pass

## 5. Secure and Test

- [ ] Restrict `/metrics` endpoint (API key or IP allowlist)
- [ ] Test `/v1/chat/completions` endpoint
- [ ] Test UI (if deployed)
- [ ] Test Prometheus metrics (if needed)

## 6. (Optional) Deploy UI and Prometheus

- [ ] Repeat build/push/deploy steps for `ui/` (Streamlit) and Prometheus if you want them public
- [ ] Or run UI locally, pointing to your App Runner API

## 7. Monitor and Maintain

- [ ] Monitor logs and metrics in AWS Console
- [ ] Rotate secrets as needed
- [ ] Update images and redeploy for new features or fixes

---

**References:**

- [AWS App Runner Docs](https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html)
- [Upstash Redis](https://upstash.com/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)

---

For ECS Fargate or Hugging Face Spaces, see `DEPLOYMENT.md` for advanced instructions.
