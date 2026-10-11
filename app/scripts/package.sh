#!/usr/bin/env bash
# Build tinyfish-growth-app.zip = app.zip + README.md + demo-video.mp4 + launch-post.md
# usage: app/scripts/package.sh <run-id>   (that run is bundled as app/sample-run/ so the dashboard works offline)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
RUN=${1:?usage: package.sh <run-id>}
OUT=$ROOT/dist
rm -rf "$OUT" && mkdir -p "$OUT/stage/app"

rsync -a --exclude .venv --exclude __pycache__ --exclude '.env' --exclude runs --exclude scripts "$ROOT/app/" "$OUT/stage/app/"
rsync -a --exclude .venv --exclude __pycache__ --exclude '.env' --exclude .pytest_cache "$ROOT/brightdata/" "$OUT/stage/app/brightdata/"
mkdir -p "$OUT/stage/app/sample-run"
rsync -a --exclude 'vo_v*' "$ROOT/runs/$RUN/" "$OUT/stage/app/sample-run/$RUN/"
if grep -rqE "sk-[A-Za-z0-9_-]{20,}|tf_[A-Za-z0-9]{20,}" "$OUT/stage"; then echo "possible secret in package" >&2; exit 1; fi
(cd "$OUT/stage/app" && zip -qr ../../app.zip .)

for f in README.md launch-post.md demo-video.mp4; do cp "$ROOT/deliverables/$f" "$OUT/$f"; done
(cd "$OUT" && zip -q tinyfish-growth-app.zip app.zip README.md launch-post.md demo-video.mp4)
rm -rf "$OUT/stage"
ls -la "$OUT"
