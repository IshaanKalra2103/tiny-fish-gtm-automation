#!/bin/sh
# uv wrapper: give every uv project mounted from the host its OWN container-local
# virtualenv at /paperclip/venvs/<project-dir-name>, unless the caller already
# set UV_PROJECT_ENVIRONMENT.
#
# Why: /workspace is the macOS host project. Without this, `uv run` in the
# container would find the host's macOS .venv (app/.venv, brightdata/.venv),
# judge it broken, and rebuild it in place with Linux binaries, which breaks
# the host. A single global UV_PROJECT_ENVIRONMENT doesn't work either: two
# projects would sync into one venv and evict each other's packages.
REAL=/usr/local/lib/uv/uv
if [ -z "${UV_PROJECT_ENVIRONMENT:-}" ]; then
  dir=""
  prev=""
  for a in "$@"; do
    case "$prev" in --project|--directory) dir="$a" ;; esac
    case "$a" in --project=*|--directory=*) dir="${a#*=}" ;; esac
    prev="$a"
  done
  [ -n "$dir" ] || dir="$PWD"
  d=$(cd "$dir" 2>/dev/null && pwd) || d=""
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    if [ -f "$d/pyproject.toml" ]; then
      UV_PROJECT_ENVIRONMENT="/paperclip/venvs/$(basename "$d")"
      export UV_PROJECT_ENVIRONMENT
      break
    fi
    d=$(dirname "$d")
  done
fi
exec "$REAL" "$@"
