#!/usr/bin/env bash
# Build the harness image, retrying on network failures (npm downloads resume via the cache mount).
set -uo pipefail
cd "$(dirname "$0")"
for attempt in 1 2 3 4; do
  echo "== build attempt $attempt"
  if docker compose build "$@"; then echo "== build ok"; exit 0; fi
  sleep 5
done
echo "== build failed after retries" >&2
exit 1
