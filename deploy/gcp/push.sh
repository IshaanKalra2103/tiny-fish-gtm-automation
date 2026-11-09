#!/usr/bin/env bash
# Deliver committed code (git archive HEAD) to the VMs over IAP. Works while ms-agent is stopped (starts it).
#
#   deploy/gcp/push.sh          agent: code -> /opt/mainstreet (workspaces/ and budget/ kept), uv sync,
#                               docker build -t mainstreet-sandbox sandbox/, restart msapi, check health
#   deploy/gcp/push.sh relay    relay: imessage/ -> /opt/ms-relay, npm ci, unit installed (NOT started)
#   deploy/gcp/push.sh all      both
#
# Only what is committed on HEAD ships; uncommitted edits stay on the Mac.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

TARGET=${1:-agent}
case $TARGET in agent | relay | all) ;; -h | --help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; *) die "unknown target: $TARGET" ;; esac

guard_account
load_project

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
REV="$(git -C "$ROOT" rev-parse --short HEAD)"
[[ -z $(git -C "$ROOT" status --porcelain 2>/dev/null) ]] || warn "the working tree has uncommitted changes; only HEAD ($REV) ships"

push_agent() {
  say "agent: HEAD $REV -> $AGENT_VM"
  git -C "$ROOT" archive --format=tar.gz -o "$TMP/mainstreet.tar.gz" HEAD
  ensure_running "$AGENT_VM"
  wait_bootstrap "$AGENT_VM"
  vm_ssh "$AGENT_VM" 'sudo touch /run/ms-idle-hold' # idle-stop must not fire during the copy
  vm_scp "$TMP/mainstreet.tar.gz" "$AGENT_VM" /tmp/mainstreet.tar.gz
  vm_ssh "$AGENT_VM" "set -e; sudo rm -rf /tmp/ms-push; mkdir -p /tmp/ms-push; tar -xzf /tmp/mainstreet.tar.gz -C /tmp/ms-push;
    sudo bash /tmp/ms-push/deploy/gcp/vm/agent-deploy.sh /tmp/ms-push; rm -rf /tmp/ms-push /tmp/mainstreet.tar.gz"
  say "agent: deployed $REV"
}

push_relay() {
  say "relay: HEAD $REV -> $RELAY_VM"
  git -C "$ROOT" archive --format=tar.gz -o "$TMP/relay.tar.gz" HEAD imessage deploy/gcp/vm
  ensure_running "$RELAY_VM"
  wait_bootstrap "$RELAY_VM"
  vm_scp "$TMP/relay.tar.gz" "$RELAY_VM" /tmp/relay.tar.gz
  vm_ssh "$RELAY_VM" "set -e; sudo rm -rf /tmp/ms-push; mkdir -p /tmp/ms-push; tar -xzf /tmp/relay.tar.gz -C /tmp/ms-push;
    sudo bash /tmp/ms-push/deploy/gcp/vm/relay-deploy.sh /tmp/ms-push; rm -rf /tmp/ms-push /tmp/relay.tar.gz"
  say "relay: deployed $REV"
}

case $TARGET in
  agent) push_agent ;;
  relay) push_relay ;;
  all) push_agent; push_relay ;;
esac
