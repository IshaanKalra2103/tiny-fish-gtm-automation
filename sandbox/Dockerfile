# MainStreet AI agent sandbox: Claude Code + the mstools CLIs, nothing else.
FROM node:22-bookworm-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code@2.1.319 && npm cache clean --force
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy PATH=/opt/venv/bin:$PATH
COPY tools /tools
RUN uv venv /opt/venv --python 3.12 && uv pip install --python /opt/venv/bin/python /tools && rm -rf /root/.cache
COPY CLAUDE.md settings.json catalog.json /sandbox/
COPY .claude /sandbox/.claude
ENV MS_WORK=/work MS_CATALOG=/sandbox/catalog.json MS_GLOBAL_BUDGET=/budget/global.json \
    DISABLE_AUTOUPDATER=1 DISABLE_TELEMETRY=1 DISABLE_ERROR_REPORTING=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
USER node
WORKDIR /sandbox
