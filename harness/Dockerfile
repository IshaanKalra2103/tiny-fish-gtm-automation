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

# Flaky network: npm retries hard, and the BuildKit cache mount keeps downloaded
# tarballs across failed attempts, so a retry resumes instead of starting over.
ENV NPM_CONFIG_FETCH_RETRIES=8 \
    NPM_CONFIG_FETCH_RETRY_MINTIMEOUT=5000 \
    NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT=120000 \
    NPM_CONFIG_FETCH_TIMEOUT=600000 \
    NPM_CONFIG_MAXSOCKETS=6

# Paperclip server + CLI.
RUN --mount=type=cache,target=/root/.npm \
    npm install --global --omit=dev --no-audit --no-fund "paperclipai@${PAPERCLIPAI_VERSION}"

# Claude Code CLI for the claude_local adapter (the CEO/orchestrator).
RUN --mount=type=cache,target=/root/.npm \
    npm install --global --omit=dev --no-audit --no-fund @anthropic-ai/claude-code@latest

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

# /usr/local/bin/uv becomes a wrapper that gives each uv project its own venv
# under /paperclip/venvs/<project> (see docker/uv-wrapper.sh). The real binaries
# move to /usr/local/lib/uv; uvx finds its sibling uv via its resolved path.
COPY docker/uv-wrapper.sh /usr/local/bin/uv-wrapper
RUN mkdir -p /usr/local/lib/uv \
  && mv /usr/local/bin/uv /usr/local/bin/uvx /usr/local/lib/uv/ \
  && mv /usr/local/bin/uv-wrapper /usr/local/bin/uv \
  && chmod +x /usr/local/bin/uv \
  && ln -s /usr/local/lib/uv/uvx /usr/local/bin/uvx

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
    UV_CACHE_DIR=/paperclip/.cache/uv

WORKDIR /workspace
EXPOSE 3100

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=10 \
  CMD curl -fsS http://127.0.0.1:3100/api/health >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "docker-entrypoint.sh"]
# Like upstream's image: start the server entry directly, configured from env
# (HOST=0.0.0.0 -> bind lan, authenticated/private). No CLI onboarding/doctor.
CMD ["node", "/usr/local/lib/node_modules/paperclipai/node_modules/@paperclipai/server/dist/index.js"]
