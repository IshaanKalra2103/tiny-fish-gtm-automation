#!/bin/bash
# ms-agent startup-script (instance metadata). Runs at every boot; does its work once.
# Installs Docker, uv and the mainstreet user. The app itself, its units and the sandbox image come from push.sh.
# push.sh waits for these lines on the serial console before its first SSH (an SSH login creates a user,
# which would take uid 1000 if it came first).
trap 'echo "mainstreet-bootstrap: FAILED"' ERR # set before -x, so the trace never shows this text
set -euxo pipefail
MARK=/var/lib/mainstreet/bootstrap.done
if [[ -f $MARK ]]; then echo "mainstreet-bootstrap: done"; exit 0; fi

# The user comes first and takes uid 1000: that is the sandbox image's "node" user, and the API and the
# container both write the bind-mounted workspaces, so they must be the same uid (as on the Mac).
# (gid 1000 is the guest agent's google-sudoers group, so the group gets any free gid.)
if ! id mainstreet >/dev/null 2>&1; then
  if getent passwd 1000 >/dev/null; then
    echo "uid 1000 is already taken by $(getent passwd 1000 | cut -d: -f1); mainstreet must be uid 1000" >&2
    false
  fi
  getent group mainstreet >/dev/null || groupadd mainstreet
  useradd -m -u 1000 -g mainstreet -s /bin/bash mainstreet
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
echo "mainstreet-bootstrap: done"
