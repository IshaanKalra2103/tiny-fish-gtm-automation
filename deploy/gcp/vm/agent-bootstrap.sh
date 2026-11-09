#!/bin/bash
# ms-agent startup-script (instance metadata). Runs at every boot; does its work once.
# Installs Docker, uv and the mainstreet user. The app itself, its units and the sandbox image come from push.sh.
set -euxo pipefail
MARK=/var/lib/mainstreet/bootstrap.done
[[ -f $MARK ]] && exit 0

# The user comes first and takes uid 1000: that is the sandbox image's "node" user, and the API and the
# container both write the bind-mounted workspaces, so they must be the same uid (as on the Mac).
if ! id mainstreet >/dev/null 2>&1; then
  if getent passwd 1000 >/dev/null; then
    echo "uid 1000 is already taken by $(getent passwd 1000 | cut -d: -f1); mainstreet must be uid 1000" >&2
    exit 1
  fi
  groupadd -g 1000 mainstreet
  useradd -m -u 1000 -g 1000 -s /bin/bash mainstreet
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends docker.io rsync curl ca-certificates python3
usermod -aG docker mainstreet
systemctl enable --now docker

if [[ ! -x /usr/local/bin/uv ]]; then
  curl -LsSf https://astral.sh/uv/0.8.4/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

install -d -o mainstreet -g mainstreet /opt/mainstreet /opt/mainstreet/workspaces /opt/mainstreet/budget
install -d -m 700 /etc/mainstreet
install -d /usr/local/lib/mainstreet /var/lib/mainstreet
touch "$MARK"
