#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# hf_deploy_ui.sh
#
# Deploys the Streamlit UI to a Hugging Face Docker Space.
#
# Strategy:
#   - The UI lives in ui/ but HF Spaces expects the Dockerfile at the repo root.
#   - This script stages the contents of ui/ into a temporary git worktree,
#     adds HF Space README.md frontmatter, and pushes it to the UI Space remote.
#   - The original project repo is never modified.
#
# Usage:
#   ./scripts/hf_deploy_ui.sh --space <hf-username/space-name> --gateway-url <url>
#
# Options:
#   --space <owner/name>         Required. Your HF UI Space identifier.
#   --gateway-url <url>          Required. Public URL of your deployed gateway.
#                                Example: https://alice-llm-gateway.hf.space
#   --token <hf-token>           HF write token (default: reads $HF_TOKEN from env)
#   --no-push                    Prepare only; skip the git push
#
# Prerequisites:
#   - git installed
#   - Hugging Face account with a second Docker Space created for the UI
#   - HF write token: https://huggingface.co/settings/tokens
#   - Gateway already deployed (see hf_deploy_gateway.sh)
#
# Examples:
#   HF_TOKEN=hf_... ./scripts/hf_deploy_ui.sh \
#     --space alice/llm-gateway-ui \
#     --gateway-url https://alice-llm-gateway.hf.space
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HF_SPACE=""
GATEWAY_URL=""
HF_TOKEN="${HF_TOKEN:-}"
NO_PUSH="false"
REMOTE_NAME="hf-ui"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --space)        HF_SPACE="$2"; shift 2 ;;
    --gateway-url)  GATEWAY_URL="$2"; shift 2 ;;
    --token)        HF_TOKEN="$2"; shift 2 ;;
    --no-push)      NO_PUSH="true"; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── preflight checks ─────────────────────────────────────────────────────────
echo "==> Checking prerequisites..."

if [[ -z "$HF_SPACE" ]]; then
  echo "ERROR: --space <hf-username/space-name> is required."
  exit 1
fi

if [[ -z "$GATEWAY_URL" ]]; then
  echo "ERROR: --gateway-url <url> is required."
  echo "Example: --gateway-url https://alice-llm-gateway.hf.space"
  exit 1
fi

if ! command -v git &>/dev/null; then
  echo "ERROR: git not found. Install git and retry."; exit 1
fi

if [[ "$NO_PUSH" == "false" && -z "$HF_TOKEN" ]]; then
  echo "ERROR: HF_TOKEN is required to push. Set it via --token or the HF_TOKEN env var."
  echo "Get a write token at: https://huggingface.co/settings/tokens"
  exit 1
fi

UI_DIR="$PROJECT_ROOT/ui"
if [[ ! -d "$UI_DIR" ]]; then
  echo "ERROR: ui/ directory not found at $UI_DIR"; exit 1
fi

echo "==> Deploying UI from: $UI_DIR"
echo "==> Target HF Space:   $HF_SPACE"
echo "==> Gateway URL:       $GATEWAY_URL"

# ── prepare a temp directory with UI contents ─────────────────────────────────
TMPDIR_DEPLOY=$(mktemp -d)
trap 'rm -rf "$TMPDIR_DEPLOY"' EXIT

echo "==> Staging UI files in $TMPDIR_DEPLOY..."

# Copy ui/ contents (Dockerfile, requirements.txt, main.py, etc.) to root of temp dir
cp -r "$UI_DIR/." "$TMPDIR_DEPLOY/"

# ── create README.md with HF Space frontmatter ───────────────────────────────
cat > "$TMPDIR_DEPLOY/README.md" <<EOF
---
title: LLM Gateway UI
emoji: 📊
colorFrom: green
colorTo: blue
sdk: docker
app_port: 8501
pinned: false
---

# LLM Gateway UI

Streamlit dashboard for the LLM Gateway — displays metrics, traces, and cache stats.
EOF

# ── inject GATEWAY_URL into Dockerfile as ENV ─────────────────────────────────
# Ensure the Streamlit UI knows where the gateway is.
DOCKERFILE="$TMPDIR_DEPLOY/Dockerfile"
if ! grep -q "GATEWAY_URL" "$DOCKERFILE"; then
  echo "==> Injecting GATEWAY_URL into UI Dockerfile..."
  # Append ENV after the existing ENV lines
  sed -i.bak "/^ENV STREAMLIT_SERVER_ADDRESS/a ENV GATEWAY_URL=${GATEWAY_URL}/v1/chat/completions" "$DOCKERFILE"
  rm -f "${DOCKERFILE}.bak"
else
  # Update existing GATEWAY_URL line
  sed -i.bak "s|ENV GATEWAY_URL=.*|ENV GATEWAY_URL=${GATEWAY_URL}/v1/chat/completions|" "$DOCKERFILE"
  rm -f "${DOCKERFILE}.bak"
fi

# ── init git repo in temp dir and commit ─────────────────────────────────────
echo "==> Initialising git repo for UI Space..."
cd "$TMPDIR_DEPLOY"
git init -b main
git config user.email "deploy-script@local"
git config user.name "HF Deploy Script"
git add -A
git commit -m "deploy: LLM Gateway UI to Hugging Face Spaces"

# ── add HF remote and push ────────────────────────────────────────────────────
HF_REPO_URL="https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}"
git remote add "$REMOTE_NAME" "$HF_REPO_URL"

if [[ "$NO_PUSH" == "true" ]]; then
  echo "==> --no-push set: skipping git push. Staged files are in: $TMPDIR_DEPLOY"
  # Prevent cleanup so user can inspect
  trap - EXIT
else
  echo "==> Pushing UI to Hugging Face Space..."
  git push "$REMOTE_NAME" main --force

  echo ""
  echo "✓ UI pushed successfully!"
  echo ""
  echo "  HF Space:  https://huggingface.co/spaces/${HF_SPACE}"
  echo "  Build log: https://huggingface.co/spaces/${HF_SPACE}/logs"
  echo ""
  echo "  Hugging Face is building your Streamlit Docker image (2-5 minutes)."
  echo "  Once live, the UI will be at:"
  echo "    https://${HF_SPACE/\//-}.hf.space"
fi
