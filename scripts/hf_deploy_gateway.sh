#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# hf_deploy_gateway.sh
#
# Deploys the FastAPI LLM Gateway to a Hugging Face Docker Space by pushing
# the project to the Space's git repository.
#
# Strategy:
#   - Adds the HF Space as a git remote (if not already added).
#   - Creates/updates the Space README.md with correct HF metadata frontmatter
#     (declares app_port: 8000, sdk: docker).
#   - Force-pushes the current branch to the Space remote (HF rebuilds on push).
#
# Usage:
#   ./scripts/hf_deploy_gateway.sh --space <hf-username/space-name>
#
# Options:
#   --space <owner/name>   Required. Your HF Space identifier.
#   --branch <branch>      Git branch to deploy (default: current branch)
#   --token <hf-token>     HF write token (default: reads $HF_TOKEN from env)
#   --no-push              Build and prepare only; skip the git push
#
# Prerequisites:
#   - git installed
#   - Hugging Face account with a Docker Space created at:
#       https://huggingface.co/spaces/<owner>/<space-name>
#   - HF write token: https://huggingface.co/settings/tokens
#   - Secrets already set in HF Space settings (OPENAI_API_KEY, REDIS_URL, etc.)
#
# Examples:
#   HF_TOKEN=hf_... ./scripts/hf_deploy_gateway.sh --space alice/llm-gateway
#   ./scripts/hf_deploy_gateway.sh --space alice/llm-gateway --branch main
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

HF_SPACE=""
BRANCH=""
HF_TOKEN="${HF_TOKEN:-}"
NO_PUSH="false"
REMOTE_NAME="hf-gateway"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── parse arguments ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --space)    HF_SPACE="$2"; shift 2 ;;
    --branch)   BRANCH="$2"; shift 2 ;;
    --token)    HF_TOKEN="$2"; shift 2 ;;
    --no-push)  NO_PUSH="true"; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── preflight checks ─────────────────────────────────────────────────────────
echo "==> Checking prerequisites..."

if [[ -z "$HF_SPACE" ]]; then
  echo "ERROR: --space <hf-username/space-name> is required."
  echo "Usage: ./scripts/hf_deploy_gateway.sh --space <owner/space-name>"
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

# ── resolve branch ────────────────────────────────────────────────────────────
cd "$PROJECT_ROOT"
if [[ -z "$BRANCH" ]]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
fi
echo "==> Deploying branch: $BRANCH"
echo "==> Target HF Space: $HF_SPACE"

# ── ensure Space README.md has correct HF frontmatter ────────────────────────
# HF requires YAML frontmatter in README.md to configure the Docker Space.
README="$PROJECT_ROOT/README.md"
FRONTMATTER="---
title: LLM Gateway
emoji: 🚀
colorFrom: blue
colorTo: green
sdk: docker
app_port: 8000
pinned: false
---"

if [[ -f "$README" ]]; then
  # Check if frontmatter already exists
  if ! head -1 "$README" | grep -q "^---"; then
    echo "==> Prepending HF Space frontmatter to README.md..."
    TMPFILE=$(mktemp)
    echo "$FRONTMATTER" > "$TMPFILE"
    echo "" >> "$TMPFILE"
    cat "$README" >> "$TMPFILE"
    mv "$TMPFILE" "$README"
    git add README.md
    git commit -m "chore: add Hugging Face Space metadata to README" || true
  else
    echo "==> README.md already has frontmatter, skipping."
  fi
else
  echo "==> Creating README.md with HF Space frontmatter..."
  echo "$FRONTMATTER" > "$README"
  echo "" >> "$README"
  echo "# LLM Gateway" >> "$README"
  echo "" >> "$README"
  echo "A production-grade LLM gateway with semantic caching, PII redaction, and cost tracking." >> "$README"
  git add README.md
  git commit -m "chore: add Hugging Face Space README" || true
fi

# ── configure HF remote ───────────────────────────────────────────────────────
HF_REPO_URL="https://user:${HF_TOKEN}@huggingface.co/spaces/${HF_SPACE}"

if git remote get-url "$REMOTE_NAME" &>/dev/null; then
  echo "==> Updating remote '$REMOTE_NAME'..."
  git remote set-url "$REMOTE_NAME" "$HF_REPO_URL"
else
  echo "==> Adding remote '$REMOTE_NAME'..."
  git remote add "$REMOTE_NAME" "$HF_REPO_URL"
fi

# ── push to HF Space ──────────────────────────────────────────────────────────
if [[ "$NO_PUSH" == "true" ]]; then
  echo "==> --no-push set: skipping git push."
else
  echo "==> Pushing to Hugging Face Space (this triggers a rebuild)..."
  git push "$REMOTE_NAME" "${BRANCH}:main" --force

  echo ""
  echo "✓ Pushed successfully!"
  echo ""
  echo "  HF Space:  https://huggingface.co/spaces/${HF_SPACE}"
  echo "  Build log: https://huggingface.co/spaces/${HF_SPACE}/logs"
  echo ""
  echo "  Hugging Face is now building your Docker image. This may take 2-5 minutes."
  echo "  Once live, the public API will be at:"
  echo "    https://${HF_SPACE/\//-}.hf.space/v1/chat/completions"
  echo ""
  echo "  Reminder: ensure these secrets are set in your Space settings:"
  echo "    OPENAI_API_KEY, ANTHROPIC_API_KEY, REDIS_URL"
  echo "    https://huggingface.co/spaces/${HF_SPACE}/settings"
fi
