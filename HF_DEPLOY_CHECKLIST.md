# Hugging Face Spaces Deployment Checklist for LLM Gateway

This checklist will guide you through deploying your FastAPI LLM Gateway to Hugging Face Spaces using Docker. Use this for portfolio/demo deployments.

---

## 1. Prerequisites

- [*] Hugging Face account
- [*] GitHub repository with your latest code
- [*] Dockerfile in project root (exposes port 8000, starts FastAPI)
- [*] Upstash or Redis Cloud account for managed Redis (get your REDIS_URL)
- [*] All API keys/secrets ready (e.g., OPENAI_API_KEY)

---

## 2. Prepare Your Repository

- [ ] Ensure all secrets are loaded via environment variables (not hardcoded)
- [*] Push latest code to GitHub
- [ ] Confirm Dockerfile uses `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`

---

## 3. Create a Hugging Face Space

- [ ] Go to https://huggingface.co/spaces
- [ ] Click "Create new Space"
- [ ] Choose "Docker" as the SDK
- [ ] Link your GitHub repo (or upload files directly)

---

## 4. Configure Space Settings

- [ ] In Space settings, add secrets as environment variables:
  - `OPENAI_API_KEY`
  - `REDIS_URL` (Upstash/Redis Cloud endpoint)
  - Any other required env vars (see `.env` or `env.example`)
- [ ] Set Docker build platform to `linux/amd64` if prompted

---

## 5. Deploy and Test

- [ ] Wait for Hugging Face to build and deploy your Space
- [ ] Visit the Space public URL (e.g., `https://<your-space>.hf.space`)
- [ ] Test `/v1/chat/completions` endpoint
- [ ] Confirm caching works (check Redis dashboard if using Upstash)

---

## 6. (Optional) Deploy Streamlit UI

- [ ] Create a separate Space for the UI using `ui/Dockerfile`
- [ ] Add required environment variables (e.g., `GATEWAY_URL`)
- [ ] Test UI at its public URL

---

## 7. Share and Maintain

- [ ] Share the public URL for demo/portfolio
- [ ] Update code and redeploy as needed

---

**References:**

- [Hugging Face Spaces Docker](https://huggingface.co/docs/hub/spaces-sdks-docker)
- [Upstash Redis](https://upstash.com/)

---
