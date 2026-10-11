#!/usr/bin/env bash
# Start the Paperclip harness in Docker. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

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
  for k in OPENAI_API_KEY OPENAI_BASE_URL; do
    v=$(grep -E "^(export )?${k}=" "$GTM_OPENAI_ENV_FILE" | tail -1 | sed -E "s/^(export )?${k}=//; s/^[\"']//; s/[\"']$//")
    if [ -n "$v" ]; then export "$k=$v"; echo "loaded ${k} from GTM_OPENAI_ENV_FILE"; fi
  done
fi

./build.sh && docker compose up -d "$@"
echo "waiting for http://localhost:${PAPERCLIP_PORT:-3100}/api/health ..."
for _ in $(seq 1 90); do
  if curl -fsS "http://localhost:${PAPERCLIP_PORT:-3100}/api/health" >/dev/null 2>&1; then
    echo "Paperclip is up: http://localhost:${PAPERCLIP_PORT:-3100}"
    exit 0
  fi
  sleep 2
done
echo "Paperclip did not become healthy; see: docker compose logs paperclip" >&2
exit 1
