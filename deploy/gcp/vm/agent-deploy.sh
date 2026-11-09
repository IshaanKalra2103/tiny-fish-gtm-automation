#!/bin/bash
# Runs as root on ms-agent, called by push.sh:  agent-deploy.sh <unpacked git archive dir>
# Syncs the code into /opt/mainstreet (workspaces/, budget/ and .venv/ are kept), installs the units,
# runs uv sync and builds the sandbox image, then restarts msapi and waits for its health check.
set -euo pipefail
SRC=${1:?usage: agent-deploy.sh <dir>}
APP=/opt/mainstreet
LIB=/usr/local/lib/mainstreet
touch /run/ms-idle-hold   # keep ms-idle from powering off mid-deploy
trap 'touch /run/ms-idle-hold' EXIT

[[ -f /var/lib/mainstreet/bootstrap.done ]] || { echo "bootstrap has not finished" >&2; exit 1; }
[[ $(id -u mainstreet) == 1000 ]] || echo "WARNING: mainstreet is not uid 1000; the sandbox may not be able to write workspaces" >&2

echo "== sync code to $APP"
rsync -a --delete --exclude /workspaces/ --exclude /budget/ --exclude /.venv/ --exclude /catalog/data/ \
  --exclude /scripts/.live/ "$SRC"/ "$APP"/
install -d -o mainstreet -g mainstreet "$APP/workspaces" "$APP/budget"
chown -R mainstreet:mainstreet "$APP"

echo "== install units and helpers"
install -d "$LIB"
install -m 755 "$APP/deploy/gcp/vm/fetch-secrets.py" "$LIB/fetch-secrets.py"
install -m 755 "$APP/deploy/gcp/vm/ms-idle.sh" "$LIB/ms-idle.sh"
for u in msapi.service ms-idle.service ms-idle.timer; do
  install -m 644 "$APP/deploy/gcp/vm/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload

echo "== uv sync"
sudo -u mainstreet -H bash -c "cd $APP && /usr/local/bin/uv sync" 2>&1 | tail -5

echo "== docker build -t mainstreet-sandbox sandbox/"
docker build -q -t mainstreet-sandbox "$APP/sandbox"
docker image prune -f >/dev/null 2>&1 || true

echo "== restart msapi"
systemctl enable ms-idle.timer msapi.service >/dev/null 2>&1
systemctl start ms-idle.timer
systemctl restart msapi.service
for _ in $(seq 1 90); do
  if body=$(curl -fsS -m 3 http://127.0.0.1:8787/api/health 2>/dev/null); then
    echo "health: $body"
    exit 0
  fi
  sleep 1
done
echo "msapi did not answer within 90 s:" >&2
journalctl -u msapi -n 40 --no-pager >&2
exit 1
