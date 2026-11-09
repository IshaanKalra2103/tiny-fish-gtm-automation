#!/bin/bash
# Runs as root on ms-relay, called by push.sh relay:  relay-deploy.sh <unpacked git archive dir>
# Installs imessage/ into /opt/ms-relay and the ms-relay unit. The unit is NOT enabled or started here
# (two relays on one Photon line double-reply); if it is already running (after cutover) it is restarted.
set -euo pipefail
SRC=${1:?usage: relay-deploy.sh <dir>}
APP=/opt/ms-relay
LIB=/usr/local/lib/mainstreet
[[ -f /var/lib/mainstreet/bootstrap.done ]] || { echo "bootstrap has not finished" >&2; exit 1; }

echo "== sync imessage/ to $APP/imessage"
install -d -o msrelay -g msrelay "$APP/imessage"
rsync -a --delete --exclude /node_modules/ --exclude /.env "$SRC/imessage/" "$APP/imessage/"
chown -R msrelay:msrelay "$APP"

echo "== npm ci"
sudo -u msrelay -H bash -c "cd $APP/imessage && npm ci --no-audit --no-fund --loglevel=error" 2>&1 | tail -5

echo "== install unit (disabled)"
install -d "$LIB"
install -m 755 "$SRC/deploy/gcp/vm/fetch-secrets.py" "$LIB/fetch-secrets.py"
install -m 644 "$SRC/deploy/gcp/vm/ms-relay.service" /etc/systemd/system/ms-relay.service
systemctl daemon-reload
if systemctl is-active --quiet ms-relay; then
  systemctl restart ms-relay
  echo "ms-relay was running; restarted"
else
  echo "ms-relay installed, not started (enabled: $(systemctl is-enabled ms-relay 2>/dev/null || true))"
fi
# Prove the Photon SDK loads, without connecting to the line.
sudo -u msrelay -H bash -c "cd $APP/imessage && node --input-type=module -e 'await import(\"spectrum-ts\"); await import(\"@spectrum-ts/imessage\")'" \
  && echo "relay dependencies load"
