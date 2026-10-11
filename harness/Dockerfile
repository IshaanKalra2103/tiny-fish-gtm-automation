# syntax=docker/dockerfile:1
#
# GTM harness: Paperclip (agent-company OS) in a slim container.
#
# Why not the upstream image? ghcr.io/paperclipai/paperclip is ~1.8 GB and
# ghcr blob downloads crawl at ~100 KB/s from this network, while a source
# build compiles a Rust runner (20+ min cold). Here we install the published
# `paperclipai` npm release on the same base image upstream uses
# (node:24-trixie-slim) and reuse upstream's entrypoint (UID remap + chown of
# the data volume, then gosu to `node`).
FROM node:24-trixie-slim

ARG PAPERCLIPAI_VERSION=2026.1005.0

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       ca-certificates gosu curl git jq ripgrep python3 tini openssh-client \
  && rm -rf /var/lib/apt/lists/* \
  && usermod -d /paperclip node \
  && mkdir -p /paperclip /workspace \
  && chown node:node /paperclip

# Paperclip server + CLI, and Claude Code for the claude_local adapter
# (the reasoning agents: CEO/orchestrator, strategist, QA personas).
RUN npm install --global --omit=dev \
       "paperclipai@${PAPERCLIPAI_VERSION}" \
       @anthropic-ai/claude-code@latest \
  && npm cache clean --force

# uv, so `process`-adapter agents can `uv run` the Python pipeline in
# /workspace/app (mounted from the host project root).
COPY --from=astral/uv:latest /uv /uvx /usr/local/bin/

# Video step deps for app/ (kept separate so earlier layers stay cached):
# espeak-ng = last-resort TTS (macOS `say` doesn't exist here), DejaVu = MoviePy text.
RUN apt-get update \
  && apt-get install -y --no-install-recommends espeak-ng fonts-dejavu-core \
  && rm -rf /var/lib/apt/lists/*

COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV NODE_ENV=production \
    HOME=/paperclip \
    HOST=0.0.0.0 \
    PORT=3100 \
    SERVE_UI=true \
    PAPERCLIP_HOME=/paperclip \
    PAPERCLIP_INSTANCE_ID=default \
    PAPERCLIP_CONFIG=/paperclip/instances/default/config.json \
    PAPERCLIP_DEPLOYMENT_MODE=authenticated \
    PAPERCLIP_DEPLOYMENT_EXPOSURE=private \
    PAPERCLIP_OPEN_ON_LISTEN=false \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    UV_PROJECT_ENVIRONMENT=/paperclip/venvs/app \
    UV_CACHE_DIR=/paperclip/.cache/uv

WORKDIR /workspace
EXPOSE 3100

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=10 \
  CMD curl -fsS http://127.0.0.1:3100/api/health >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "docker-entrypoint.sh"]
# `run --yes --bind lan`: first boot onboards non-interactively with a 0.0.0.0
# listener (a loopback bind is unreachable through Docker's port mapping);
# later boots reuse /paperclip/instances/default/config.json.
CMD ["paperclipai", "run", "--yes", "--bind", "lan"]
