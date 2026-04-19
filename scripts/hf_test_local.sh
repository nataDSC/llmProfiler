#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# hf_test_local.sh
#
# Builds and smoke-tests the LLM Gateway in Docker locally before deploying to
# Hugging Face Spaces. Requires Docker Desktop and a running Redis / Upstash URL.
#
# Usage:
#   ./scripts/hf_test_local.sh [--redis <REDIS_URL>] [--echo]
#
# Options:
#   --redis <url>   Override the Redis URL (default: reads $REDIS_URL from env)
#   --echo          Start the gateway in ECHO_MODE (no real API key required)
#
# Examples:
#   REDIS_URL=rediss://... ./scripts/hf_test_local.sh
#   ./scripts/hf_test_local.sh --redis rediss://... --echo
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

IMAGE="llm-gateway:hf-test"
CONTAINER="llm-gateway-hf-test"
PORT=8000
ECHO_MODE="false"
REDIS_URL="${REDIS_URL:-}"

# ── parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --redis) REDIS_URL="$2"; shift 2 ;;
    --echo)  ECHO_MODE="true"; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── preflight checks ─────────────────────────────────────────────────────────
echo "==> Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker not found. Install Docker Desktop and retry."; exit 1
fi

if [[ "$ECHO_MODE" == "false" ]]; then
  if [[ -z "${OPENAI_API_KEY:-}" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "ERROR: Set OPENAI_API_KEY or ANTHROPIC_API_KEY, or pass --echo for test mode."
    exit 1
  fi
  if [[ -z "$REDIS_URL" ]]; then
    echo "ERROR: Set REDIS_URL (Upstash/Redis Cloud) or pass --echo for test mode."
    exit 1
  fi
fi

# ── build ─────────────────────────────────────────────────────────────────────
# Build for the native host platform so local tests run at full speed.
# HF deploy scripts handle linux/amd64 separately.
echo "==> Building Docker image (native platform)..."
docker build -t "$IMAGE" .

# ── clean up any previous test container ─────────────────────────────────────
docker rm -f "$CONTAINER" 2>/dev/null || true

# ── run ───────────────────────────────────────────────────────────────────────
echo "==> Starting container on port $PORT..."
docker run -d --name "$CONTAINER" \
  -p "$PORT:8000" \
  -e "OPENAI_API_KEY=${OPENAI_API_KEY:-}" \
  -e "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}" \
  -e "REDIS_URL=${REDIS_URL:-redis://localhost:6379/0}" \
  -e "ECHO_MODE=${ECHO_MODE}" \
  "$IMAGE"

# ── wait for gateway to be ready ─────────────────────────────────────────────
echo "==> Waiting for gateway to be ready..."
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$PORT/health" &>/dev/null; then
    echo "==> Gateway is up!"
    break
  fi
  sleep 1
  if [[ $i -eq 30 ]]; then
    echo "ERROR: Gateway did not become healthy. Container logs:"
    docker logs "$CONTAINER"
    docker rm -f "$CONTAINER"
    exit 1
  fi
done

# ── smoke test ────────────────────────────────────────────────────────────────
echo "==> Running smoke test..."

if [[ "$ECHO_MODE" == "true" ]]; then
  PAYLOAD='{"model":"echo","messages":[{"role":"user","content":"ping"}]}'
else
  PAYLOAD='{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Say hello in one word."}]}'
fi

RESPONSE=$(curl -sf -X POST "http://localhost:$PORT/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD") || { echo "ERROR: Smoke test request failed."; docker logs "$CONTAINER"; docker rm -f "$CONTAINER"; exit 1; }

echo "==> Response received:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"

# ── clean up ──────────────────────────────────────────────────────────────────
echo "==> Stopping and removing test container..."
docker rm -f "$CONTAINER"

echo ""
echo "✓ Local test passed. Ready to deploy to Hugging Face Spaces."
echo "  Next: ./scripts/hf_deploy_gateway.sh --space <your-hf-username/space-name>"
