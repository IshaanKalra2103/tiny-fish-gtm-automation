#!/usr/bin/env bash
# Start the Paperclip harness in Docker. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

# Restore tokens/sessions from the device vault (macOS Keychain) before anything is generated,
# so a fresh checkout reuses the same secrets as the existing data volume. See vault.py.
if command -v security >/dev/null 2>&1 && command -v uv >/dev/null 2>&1; then
  uv run vault.py restore >/dev/null 2>&1 || echo "vault restore skipped (run: uv run harness/vault.py list)" >&2
fi

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  sed -i.bak "s|^BETTER_AUTH_SECRET=.*|BETTER_AUTH_SECRET=$(openssl rand -hex 32)|" .env
  sed -i.bak "s|^PAPERCLIP_TOOL_ACTION_SIGNING_SECRET=.*|PAPERCLIP_TOOL_ACTION_SIGNING_SECRET=$(openssl rand -hex 32)|" .env
  sed -i.bak "s|^PAPERCLIP_AGENT_JWT_SECRET=.*|PAPERCLIP_AGENT_JWT_SECRET=$(openssl rand -hex 32)|" .env
  rm -f .env.bak
  echo "wrote harness/.env with fresh secrets"
fi

# Fill provider keys from the calling shell if .env leaves them empty.
for k in ANTHROPIC_API_KEY TINYFISH_API_KEY ELEVENLABS_API_KEY BRIGHTDATA_API_KEY AGENTMAIL_API_KEY; do
  v="${!k:-}"
  if [ -n "$v" ] && grep -q "^${k}=$" .env; then
    sed -i.bak "s|^${k}=$|${k}=${v}|" .env && rm -f .env.bak
    echo "copied ${k} from environment into harness/.env"
  fi
done

# OpenAI key: never copied into harness/.env. Either export OPENAI_API_KEY in the
# calling shell, or point GTM_OPENAI_ENV_FILE at an existing .env; only
# OPENAI_API_KEY / OPENAI_BASE_URL are taken from it, at launch, into compose's
# process env (nothing is printed or written).
if [ -n "${GTM_OPENAI_ENV_FILE:-}" ]; then
  [ -f "$GTM_OPENAI_ENV_FILE" ] || { echo "GTM_OPENAI_ENV_FILE not found" >&2; exit 1; }
  # Source it in a subshell (shell quoting and inline "# comments" parse correctly;
  # a grep/sed parser kept the comment as part of the key -> 401) and keep only these two.
  for k in OPENAI_API_KEY OPENAI_BASE_URL; do
    v=$(set -a; . "$GTM_OPENAI_ENV_FILE" >/dev/null 2>&1; eval "printf %s \"\${$k:-}\"")
    if [ -n "$v" ]; then export "$k=$v"; echo "loaded ${k} from GTM_OPENAI_ENV_FILE"; fi
  done
fi

./build.sh && docker compose up -d "$@"
echo "waiting for http://localhost:${PAPERCLIP_PORT:-3100}/api/health ..."
for _ in $(seq 1 90); do
  if curl -fsS "http://localhost:${PAPERCLIP_PORT:-3100}/api/health" >/dev/null 2>&1; then
    echo "Paperclip is up: http://localhost:${PAPERCLIP_PORT:-3100}"
    echo "preparing campaign workers (first install may take several minutes) ..."
    docker compose exec -T --user node -w /workspace/app paperclip uv sync --frozen
    echo "Workers installed. Run uv run harness/campaign.py doctor from the repository root."
    exit 0
  fi
  sleep 2
done
echo "Paperclip did not become healthy; see: docker compose logs paperclip" >&2
exit 1
