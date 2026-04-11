# 🚀 LLM Gateway Deployment Plan

This plan covers production-grade deployment to AWS (App Runner as default, ECS Fargate as advanced), with a Hugging Face Spaces section for portfolio/demo deployment. All recommendations are NAT-free and Mac M-series compatible.

---

## 1. Managed Redis: Upstash (Default) or Redis Cloud

- Use Upstash (serverless Redis) for hybrid cache. No VPC/NAT required, generous free tier.
- For interview/enterprise: ElastiCache (requires VPC, no perpetual free tier, more complex networking).

---

## 2. AWS App Runner (Recommended)

- Fastest path to a live, scalable, production-grade API.
- Handles load balancing, SSL, auto-scaling, and public URL out of the box.
- No VPC/NAT required for outbound internet (OpenAI/Anthropic calls work by default).
- Use Upstash for Redis to avoid VPC/NAT complexity.

### Steps:

1. **Build Docker Image for AWS (Mac M1/M2/M3):**
   ```bash
   docker buildx build --platform linux/amd64 -t llm-gateway:latest .
   ```
2. **Push to AWS ECR:**
   - Create ECR repo (`llm-gateway`).
   - Authenticate and push image.
3. **Deploy with App Runner:**
   - Point to ECR image.
   - Set resources (1 vCPU, 2GB RAM is enough for FastAPI).
   - Add environment variables: `OPENAI_API_KEY`, `REDIS_URL`, etc.
   - Use AWS Secrets Manager for secrets (see below).
4. **Secrets Management:**
   - Store API keys in AWS Secrets Manager.
   - Grant App Runner IAM role permission to read secrets.
   - App Runner injects secrets as env vars at runtime.
5. **Protect /metrics Endpoint:**
   - Do not expose `/metrics` publicly. Use API key or IP whitelist.

---

## 3. ECS Fargate (Advanced/Enterprise)

- Use only if you want to practice VPC, subnets, ALB, and private networking.
- Place tasks in public subnets with public IPs and an Internet Gateway to avoid NAT costs.
- Use VPC Endpoints for AWS-to-AWS traffic (ECR, Secrets Manager) to avoid NAT.
- ElastiCache requires VPC and VPC Connector if used with App Runner.

---

## 4. Hugging Face Spaces (Demo/Portfolio)

- Create a Space, select Docker as SDK.
- Use the same Dockerfile as AWS (build for linux/amd64).
- Add secrets (`OPENAI_API_KEY`, `REDIS_URL`) in Space settings.
- Hugging Face handles SSL and public URL.

---

## 5. Checklist

- [ ] Install AWS CLI (`brew install awscli`)
- [ ] Have AWS account with credit card
- [ ] Docker Desktop running
- [ ] IAM user with AdministratorAccess
- [ ] Upstash or Redis Cloud account for managed Redis

---

## 6. Networking/NAT-Free Summary

| Component             | Strategy                                                   |
| :-------------------- | :--------------------------------------------------------- |
| **Compute**           | **AWS App Runner** (no NAT needed for OpenAI/Anthropic)    |
| **Outbound (OpenAI)** | App Runner's default managed internet                      |
| **Redis**             | **Upstash** (no VPC/NAT needed)                            |
| **Secrets**           | **AWS Secrets Manager** (App Runner integration, IAM role) |

- If using ECS Fargate, use public subnets + IGW, not NAT.
- For AWS-to-AWS traffic, use VPC Endpoints (cheaper than NAT).

---

## 7. Security Notes

- Never hardcode secrets in code or Docker images.
- Use environment variables and AWS Secrets Manager.
- Protect internal endpoints (e.g., `/metrics`).

---

## 8. Hugging Face Spaces: Quick Steps

1. Create a new Space (Docker template).
2. Link GitHub repo.
3. Add secrets in Space settings.
4. Deploy and share public URL.

---

## 9. References

- [AWS App Runner Docs](https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html)
- [Upstash Redis](https://upstash.com/)
- [Hugging Face Spaces Docker](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)

---

## 10. First Push: AWS Deployment Checklist

Follow these steps for your first AWS App Runner deployment:

### 1. Build Docker Image for AWS (Mac M1/M2/M3)

- [ ] Open a terminal in your project root.
- [ ] Run:
  ```bash
  docker buildx build --platform linux/amd64 -t llm-gateway:latest .
  ```

### 2. Push Image to AWS ECR

- [ ] Log in to AWS ECR:
  ```bash
  aws ecr get-login-password --region <your-region> | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.<your-region>.amazonaws.com
  ```
- [ ] Create ECR repo if not already done:
  ```bash
  aws ecr create-repository --repository-name llm-gateway
  ```
- [ ] Tag your image:
  ```bash
  docker tag llm-gateway:latest <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/llm-gateway:latest
  ```
- [ ] Push your image:
  ```bash
  docker push <your-account-id>.dkr.ecr.<your-region>.amazonaws.com/llm-gateway:latest
  ```

### 3. Deploy with AWS App Runner

- [ ] Go to AWS Console → App Runner → Create Service
- [ ] Select "Container registry" and choose your ECR image
- [ ] Set service name (e.g., llm-gateway)
- [ ] Set resources (1 vCPU, 2GB RAM is enough)
- [ ] Add environment variables:
  - `OPENAI_API_KEY`
  - `REDIS_URL` (Upstash/Redis Cloud)
  - Any others needed
- [ ] (Recommended) Use AWS Secrets Manager for secrets and grant App Runner IAM role permission
- [ ] Click "Next" and "Create & deploy"

### 4. Test Your Deployment

- [ ] Wait for App Runner to finish deploying (watch logs for errors)
- [ ] Visit the public URL provided by App Runner
- [ ] Test `/v1/chat/completions` endpoint
- [ ] Test UI if deployed

### 5. Secure /metrics Endpoint

- [ ] Ensure `/metrics` is not exposed publicly (use API key or IP whitelist)

---

You are now live on AWS! For future updates, repeat steps 1–2 (build and push), then App Runner will auto-deploy the new image.
