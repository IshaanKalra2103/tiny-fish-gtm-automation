#!/bin/sh
# Prep, build and render in one go:  ./make.sh [film.toml] [out.mp4]
set -e
cd "$(dirname "$0")"
FILM="${1:-film.toml}"
OUT="${2:-out.mp4}"
uv run prep.py "$FILM"
cargo build --release --quiet
FILM="$FILM" ./target/release/film render -o "$OUT"
