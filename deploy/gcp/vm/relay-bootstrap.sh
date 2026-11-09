#!/bin/bash
# ms-relay startup-script (instance metadata). Runs at every boot; does its work once.
# Installs Node 22 and the msrelay user. The relay code and its (disabled) unit come from push.sh relay.
# The result also goes to the guest attribute mainstreet/bootstrap (the serial log can drop short output).
report() {
  echo "mainstreet-bootstrap: $1"
  curl -fsS -m 5 -X PUT --data "$1" -H "Metadata-Flavor: Google" \
    http://metadata.google.internal/computeMetadata/v1/instance/guest-attributes/mainstreet/bootstrap >/dev/null 2>&1 || true
}
trap 'report FAILED' ERR # set before -x, so the trace never shows the marker text
set -euxo pipefail
MARK=/var/lib/mainstreet/bootstrap.done
if [[ -f $MARK ]]; then report done; exit 0; fi

id msrelay >/dev/null 2>&1 || useradd -r -m -d /var/lib/msrelay -s /usr/sbin/nologin msrelay

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends rsync curl ca-certificates gnupg python3
if ! node --version 2>/dev/null | grep -q '^v22\.'; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

# e2-micro has 1 GB of RAM; a swap file keeps npm ci from being OOM-killed.
if [[ ! -f /swapfile ]]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

install -d -o msrelay -g msrelay /opt/ms-relay
install -d /usr/local/lib/mainstreet /var/lib/mainstreet
touch "$MARK"
report done
