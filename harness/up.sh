#!/usr/bin/env bash
# Start the Paperclip harness in Docker. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  sed -i.bak "s|^BETTER_AUTH_SECRET=.*|BETTER_AUTH_SECRET=$(openssl rand -hex 32)|" .env
  sed -i.bak "s|^PAPERCLIP_TOOL_ACTION_SIGNING_SECRET=.*|PAPERCLIP_TOOL_ACTION_SIGNING_SECRET=$(openssl rand -hex 32)|" .env
  rm -f .env.bak
  echo "wrote harness/.env with fresh secrets"
fi

# Fill provider keys from the calling shell if .env leaves them empty.
for k in ANTHROPIC_API_KEY OPENAI_API_KEY TINYFISH_API_KEY ELEVENLABS_API_KEY; do
  v="${!k:-}"
  if [ -n "$v" ] && grep -q "^${k}=$" .env; then
    sed -i.bak "s|^${k}=$|${k}=${v}|" .env && rm -f .env.bak
    echo "copied ${k} from environment into harness/.env"
  fi
done

docker compose up -d --build "$@"
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
