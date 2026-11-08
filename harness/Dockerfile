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

# iMessage read receipts: Paperclip's Photon adapter shows typing but never marks
# chats read, although @photon-ai/advanced-imessage has chats.markRead(). Mark the
# chat read right before the typing bubble starts (best-effort). The grep fails the
# build if an upgrade moves the anchor, so the patch can't silently disappear.
RUN F=/usr/local/lib/node_modules/paperclipai/node_modules/@paperclipai/server/dist/services/photon/adapter.js \
  && sed -i 's|        await this.refreshTyping(id, false);|        await this.client.chats.markRead(this.decodeThreadId(id).chatGuid).catch(() => { });\n        await this.refreshTyping(id, false);|' "$F" \
  && grep -q "chats.markRead(this.decodeThreadId(id).chatGuid)" "$F"

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

# Agent CLIs on PATH, reusing the binaries paperclipai already bundles for its
# claude_local/codex_local adapters (no second download).
RUN NM=/usr/local/lib/node_modules/paperclipai/node_modules \
  && ln -sf "$(ls -d $NM/@openai/codex-linux-*/vendor/*/bin/codex | head -1)" /usr/local/bin/codex \
  && codex --version

# claude_local runs Claude through claude-agent-acp, which does NOT use the global CLI
# above: it spawns the native binary bundled with paperclipai's @anthropic-ai/claude-agent-sdk
# (claude-agent-acp 0.73.0 pins 0.3.257 = Claude Code 2.1.257). The API rejects
# claude-opus-5-5 from Claude Code < 2.1.280, so swap in a newer SDK + binary in place.
# (CLAUDE_CODE_EXECUTABLE would also work, but Paperclip's ACP launch env drops it.)
ARG CLAUDE_AGENT_SDK_VERSION=0.3.296
RUN --mount=type=cache,target=/root/.npm \
    D=/usr/local/lib/node_modules/paperclipai/node_modules/@anthropic-ai \
  && P="claude-agent-sdk-linux-$(node -p process.arch)" \
  && cd /tmp \
  && for p in claude-agent-sdk "$P"; do \
       t=$(npm pack --silent "@anthropic-ai/$p@${CLAUDE_AGENT_SDK_VERSION}") \
       && rm -rf "$D/$p" && mkdir "$D/$p" \
       && tar -xzf "$t" -C "$D/$p" --strip-components=1 --no-same-owner && rm "$t" || exit 1; \
     done \
  && "$D/$P/claude" --version

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
