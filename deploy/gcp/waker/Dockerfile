# ms-waker: Cloud Run front for the agent VM. Built by Cloud Build from deploy/gcp/waker (setup.sh).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY mswaker ./mswaker
EXPOSE 8080
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn --factory mswaker.app:from_env --host 0.0.0.0 --port ${PORT:-8080} --timeout-keep-alive 75 --no-access-log"]
