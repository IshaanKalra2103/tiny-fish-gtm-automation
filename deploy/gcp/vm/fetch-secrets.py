#!/usr/bin/python3
"""ExecStartPre helper: Secret Manager -> a root-written env file (mode 600). Never prints a value.

    fetch-secrets.py agent   -> /etc/mainstreet/agent.env        (read by systemd for msapi.service)
    fetch-secrets.py relay   -> /opt/ms-relay/imessage/.env      (owned by msrelay; npm start reads it)

Auth is the VM's service account via the metadata server, so no gcloud and no key files on the VM.
"""
import base64
import json
import os
import pwd
import sys
import time
import urllib.error
import urllib.request

META = "http://metadata.google.internal/computeMetadata/v1/"
PROFILES = {
    "agent": {
        "out": "/etc/mainstreet/agent.env", "owner": "root",
        "secrets": {"CLAUDE_CODE_OAUTH_TOKEN": "claude-code-oauth-token", "TINYFISH_API_KEY": "tinyfish-api-key",
                    "OPENROUTER_API_KEY": "openrouter-api-key", "AGENTMAIL_API_KEY": "agentmail-api-key",
                    "MS_RELAY_SECRET": "ms-relay-secret"},
        "metadata": {},
        "fixed": {},
    },
    "relay": {
        "out": "/opt/ms-relay/imessage/.env", "owner": "msrelay",
        "secrets": {"PROJECT_ID": "photon-project-id", "PROJECT_SECRET": "photon-project-secret",
                    "MS_RELAY_SECRET": "ms-relay-secret"},
        "metadata": {"AGENT_API_URL": "agent-api-url"},
        # Read by imessage/src/index.ts once it passes a timeout through (relay.ts TIMEOUT_MS is 300 s today).
        "fixed": {"RELAY_TIMEOUT_MS": "420000"},
    },
}


def get(url: str, headers: dict, tries: int = 10) -> bytes:
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404) or i == tries - 1:
                raise
        except OSError:
            if i == tries - 1:
                raise
        time.sleep(3)
    raise RuntimeError("unreachable")


def meta(path: str) -> str:
    return get(META + path, {"Metadata-Flavor": "Google"}).decode()


def quote(v: str) -> str:
    if v and all(c.isalnum() or c in "-_.:/+=@,~" for c in v):
        return v
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def main(profile: str) -> int:
    p = PROFILES[profile]
    project = meta("project/project-id")
    token = json.loads(meta("instance/service-accounts/default/token"))["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    env: dict[str, str] = {}
    for var, secret in p["secrets"].items():
        url = f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets/{secret}/versions/latest:access"
        try:
            body = json.loads(get(url, auth))
        except urllib.error.HTTPError as e:
            print(f"fetch-secrets: {secret}: HTTP {e.code}", file=sys.stderr)
            return 1
        env[var] = base64.b64decode(body["payload"]["data"]).decode().strip()
    for var, attr in p["metadata"].items():
        env[var] = meta(f"instance/attributes/{attr}").strip()
    env.update(p["fixed"])
    out = p["out"]
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("".join(f"{k}={quote(v)}\n" for k, v in env.items()))
    os.chmod(tmp, 0o600)
    pw = pwd.getpwnam(p["owner"])
    os.chown(tmp, pw.pw_uid, pw.pw_gid)
    os.replace(tmp, out)
    print(f"fetch-secrets: wrote {len(env)} variables to {out} (mode 600, owner {p['owner']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "agent"))
