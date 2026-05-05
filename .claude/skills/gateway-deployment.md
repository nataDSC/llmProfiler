---
name: gateway-deployment
description: Use when working on Dockerfile, docker-compose*.yml, scripts/hf_deploy_gateway.sh, scripts/hf_deploy_ui.sh, scripts/hf_test_local.sh, prometheus.yml, or any AWS/HF Spaces deployment task. Covers the Mac-to-cloud build trap, service dependency ordering, secrets management, and the planned AWS App Runner path.
---

# Gateway Deployment Skill

You are working on the **containerization and cloud deployment** of an LLM gateway stack. This skill covers the Docker Compose local setup, Hugging Face Spaces deployment (live), and the planned AWS deployment (not yet executed).

---

## The Mac ARM → cloud x86 build trap

This project is developed on a Mac Pro (ARM/Apple Silicon). Cloud targets (HF Spaces, AWS) run on x86. An ARM image will crash on x86 with `Exec format error`.

**Always build for linux/amd64 when pushing to any cloud:**

```bash
docker buildx build --platform linux/amd64 -t <image>:<tag> .
```

Verify the deploy scripts (`scripts/hf_deploy_gateway.sh`, `scripts/hf_deploy_ui.sh`) include the `--platform linux/amd64` flag before running them. If they don't, add it.

For local dev on your Mac, omit the platform flag — local images run on ARM natively and are faster to build.

---

## Docker Compose service topology

```
docker-compose.yml defines four services:

cache     ← Redis 8.4-alpine (ports 6379, 8001)
  ↑
gateway   ← FastAPI app (port 8000), depends_on: cache (service_healthy)
  ↑
ui        ← Streamlit app (port 8501), depends_on: gateway
prometheus ← Prometheus (port 9090), depends_on: gateway
```

**Dependency ordering is enforced** — `gateway` will not start until Redis responds to `redis-cli ping`. Do not remove or weaken the `service_healthy` condition; startup races cause confusing "Connection Refused" errors.

Ports:
- `8000` — FastAPI gateway (Swagger UI at `/docs`)
- `8501` — Streamlit UI
- `9090` — Prometheus
- `6379` — Redis (exposed for local tooling)
- `8001` — RedisInsight (exposed for debugging vector keys)

### Internal Docker DNS
Services communicate by name, not IP:
- Gateway → Redis: `redis://cache:6379`
- UI → Gateway: `http://gateway:8000/v1/chat/completions`
- Prometheus → Gateway: `http://gateway:8000/metrics`

Never hardcode IPs. The env var `GATEWAY_URL` in the UI service and `REDIS_URL` in the gateway service are injected by Docker Compose environment blocks.

### Full stack launch
```bash
cp env.example .env          # add your API keys
docker-compose up --build    # first run or after code changes
docker-compose up            # subsequent runs (no rebuild)
docker-compose up cache -d   # start only Redis (for local dev without containers)
```

---

## ECHO_MODE — test without burning API credits

Set `ECHO_MODE=true` in the gateway environment to make the OpenAI adapter echo requests without calling the real API:

```yaml
# docker-compose.yml gateway service
environment:
  - ECHO_MODE=true
```

Use this when testing infra changes (networking, Redis, Prometheus) where LLM responses don't matter. The gateway still exercises the full request path including cache, PII, and metrics.

---

## Hugging Face Spaces (live)

The gateway and UI are deployed as separate HF Spaces using Docker as the SDK.

**Port**: HF Spaces requires the app to declare its port in the `README.md` YAML frontmatter:
```yaml
app_port: 8000   # gateway
app_port: 8501   # UI
```
Do not change this without updating the Space metadata — HF will not be able to route traffic to the app.

**Secrets**: API keys and `REDIS_URL` are stored in HF Space Settings → Variables and Secrets. They are injected as environment variables at container startup. Never commit `.env` or hardcode secrets.

**Redis**: HF Spaces containers are ephemeral — local Redis state is lost on restart or redeploy. The live deployment must use an external managed Redis (Upstash or Redis Cloud). `REDIS_URL` in the HF secrets should point to the external instance.

**Deploy scripts**: `scripts/hf_deploy_gateway.sh` and `scripts/hf_deploy_ui.sh` handle the Git-based push to HF. `scripts/hf_test_local.sh` runs a local smoke test before pushing. Always run the local test first.

**HF Dev Mode**: HF Spaces supports Dev Mode (SSH or VS Code remote) for editing without a full redeploy. Use it for UI tweaks; use a full push for backend changes.

---

## Prometheus configuration

`prometheus.yml` configures Prometheus to scrape the gateway's `/metrics` endpoint. The scrape target is `gateway:8000` (internal Docker DNS). Do not expose `/metrics` publicly in production — it reveals internal performance data. If moving to AWS, place the metrics endpoint behind an IP allowlist or API key.

---

## AWS deployment (planned, not yet executed)

Per `docs/aws_deployment_plan.md`, the target architecture is:

| Component | Service |
|---|---|
| Compute | AWS App Runner |
| Cache | Upstash (external Redis, no VPC needed) |
| Secrets | AWS Secrets Manager (injected as env vars by App Runner) |
| Images | AWS ECR (Elastic Container Registry) |

**Why App Runner over ECS Fargate**: App Runner manages load balancing, SSL, and auto-scaling automatically. It avoids the need for a NAT Gateway (saves ~$32/month) because App Runner has built-in outbound internet access for calls to OpenAI/Anthropic.

**Build and push to ECR**:
```bash
# Authenticate
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

# Build for x86 and push
docker buildx build --platform linux/amd64 \
  -t <account>.dkr.ecr.us-east-1.amazonaws.com/llm-gateway:latest \
  --push .
```

**No NAT Gateway**: Use Upstash for Redis (lives outside AWS VPC, reachable over public internet). This means the gateway doesn't need a VPC at all. If ElastiCache is used later, add a VPC Connector to App Runner — but avoid it to keep costs down.

**IAM**: the App Runner execution role needs `secretsmanager:GetSecretValue` to read API keys at startup. Set this up before first deploy.

---

## Open work items owned by this domain

- [ ] **Execute AWS App Runner deployment** per `docs/aws_deployment_plan.md`: build x86 image → push to ECR → configure App Runner → set secrets → verify live endpoint.
- [ ] **Verify deploy scripts use `--platform linux/amd64`**: check `scripts/hf_deploy_gateway.sh` and `scripts/hf_deploy_ui.sh` — add the flag if missing.
- [ ] **Protect `/metrics` endpoint**: add IP allowlist or simple API key middleware before any public AWS deployment.
