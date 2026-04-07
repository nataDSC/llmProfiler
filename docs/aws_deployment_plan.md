# AWS Deployment Plan for LLM Gateway

This document outlines a recommended approach for deploying the LLM Gateway (FastAPI, Redis, Prometheus) on AWS for production and demo use cases.

---

## 1. Architecture Overview

- **FastAPI App**: Containerized (Docker)
- **Redis**: AWS ElastiCache (managed Redis) or self-hosted in ECS
- **Prometheus**: Containerized (Docker), optional for production
- **Load Balancer**: AWS Application Load Balancer (ALB)
- **Orchestration**: AWS ECS (Fargate) or AWS App Runner
- **Secrets/Config**: AWS Secrets Manager or SSM Parameter Store
- **CI/CD**: GitHub Actions or AWS CodePipeline

---

## 2. Steps to Deploy

### A. Containerization

- Ensure all services (FastAPI, Prometheus) have Dockerfiles.
- Use `docker-compose.yml` for local dev/testing.

### B. AWS Resources

1. **ECR (Elastic Container Registry)**
   - Push FastAPI and Prometheus images to ECR.
2. **ElastiCache (Redis)**
   - Provision a Redis cluster (single-node for dev, multi-AZ for prod).
3. **ECS (Fargate) or App Runner**
   - Create ECS Task Definitions for FastAPI and Prometheus.
   - Set environment variables for API keys, Redis URL, etc.
   - Configure service discovery or use internal VPC networking.
4. **ALB (Application Load Balancer)**
   - Route external traffic to FastAPI service.
5. **Prometheus**
   - Expose `/metrics` endpoint internally or securely for monitoring.
6. **Secrets Management**
   - Store API keys and sensitive config in AWS Secrets Manager or SSM.

### C. CI/CD Pipeline

- Build and push Docker images on commit (GitHub Actions or CodeBuild).
- Deploy to ECS/App Runner using IaC (CloudFormation, CDK, or Terraform).

---

## 3. Example Workflow

1. **Build & Push**
   - `docker build -t <repo>/llm-gateway:latest .`
   - `docker push <repo>/llm-gateway:latest`
2. **Deploy**
   - Update ECS Task Definition with new image tag.
   - Redeploy ECS service (via console, CLI, or pipeline).
3. **Monitor**
   - Use Prometheus/Grafana for metrics.
   - Use AWS CloudWatch for logs and health checks.

---

## 4. Security & Best Practices

- Use IAM roles for ECS tasks (least privilege).
- Restrict Redis access to VPC/internal only.
- Use HTTPS via ALB.
- Rotate secrets regularly.
- Enable auto-scaling for ECS services.

---

## 5. Cost Considerations

- Fargate/App Runner: Pay per usage, scales to zero for demo.
- ElastiCache: On-demand, can use free tier for dev.
- Use spot instances for non-critical workloads.

---

## 6. References

- [AWS ECS Fargate Docs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [AWS App Runner](https://docs.aws.amazon.com/apprunner/latest/dg/)
- [ElastiCache Redis](https://docs.aws.amazon.com/elasticache/latest/red-ug/)
- [Prometheus on ECS](https://prometheus.io/docs/prometheus/latest/installation/)

---

This plan can be adapted for more advanced needs (multi-region, blue/green deploys, etc.) as the project grows.
