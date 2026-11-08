"""Output contract for every tool CLI: exactly one JSON line on stdout, progress on stderr."""
import argparse
import json
import sys
from typing import Callable, NoReturn

from pydantic import ValidationError


class ToolError(Exception):
    """A failure the agent should read as a plain sentence."""


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def emit(obj: dict) -> None:
    print(json.dumps(obj, default=str), flush=True)


def run(fn: Callable[[argparse.Namespace], dict], parser: argparse.ArgumentParser) -> NoReturn:
    args = parser.parse_args()
    try:
        result = fn(args)
    except (ToolError, ValidationError) as e:
        emit({"ok": False, "error": str(e)})
        sys.exit(1)
    emit({"ok": True, **(result or {})})
    sys.exit(0)
