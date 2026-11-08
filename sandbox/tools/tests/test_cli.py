import json
import subprocess
import sys

PROG = """
import argparse
from mstools.cli import ToolError, run
p = argparse.ArgumentParser()
p.add_argument("mode")
def fn(a):
    if a.mode == "bad":
        raise ToolError("nope")
    return {"value": 1}
run(fn, p)
"""


def call(mode):
    return subprocess.run([sys.executable, "-c", PROG, mode], capture_output=True, text=True)


def test_cli_ok_and_error_lines():
    ok = call("good")
    assert ok.returncode == 0
    lines = ok.stdout.strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0]) == {"ok": True, "value": 1}
    bad = call("bad")
    assert bad.returncode == 1
    assert json.loads(bad.stdout.strip()) == {"ok": False, "error": "nope"}
