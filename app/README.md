# gtm: agent-led growth loop on TinyFish

Give it a brand URL and a niche. It finds what's trending, learns the winning short-video format, renders a 9:16 video, has 3 synthetic audience personas review it, revises until they pass, and stops at a human approval gate. Publishing is simulated.

## Run

```bash
cp .env.example .env          # add TINYFISH_API_KEY and OPENAI_API_KEY
uv sync
uv run gtm run --brand-url https://www.tinyfish.ai/ --niche "AI browser agents"
uv run gtm serve              # dashboard at http://localhost:8501/
uv run gtm approve <run-id>   # human approval: marks the draft ready to publish
```

One role at a time (this is how the Paperclip harness drives it):

```bash
uv run gtm agent research|analysis|strategy|video|qa|publish|learn --run <run-id>
```

Every command prints one JSON line to stdout (`{"ok": true, ...}`, or `{"ok": false, "error": ...}` with exit code 1). Progress goes to stderr. Run artifacts land in `runs/<run-id>/`.
