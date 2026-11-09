#!/bin/bash
# ms-relay startup-script (instance metadata). Runs at every boot; does its work once.
# Installs Node 22 and the msrelay user. The relay code and its (disabled) unit come from push.sh relay.
trap 'echo "mainstreet-bootstrap: FAILED"' ERR # set before -x, so the trace never shows this text
set -euxo pipefail
MARK=/var/lib/mainstreet/bootstrap.done
if [[ -f $MARK ]]; then echo "mainstreet-bootstrap: done"; exit 0; fi

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
echo "mainstreet-bootstrap: done"
