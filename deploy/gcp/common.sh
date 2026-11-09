# Sourced by setup.sh, push.sh and ctl.sh.
# Every gcloud call here uses the separate config dir ~/.config/gcloud-aisb (the personal Google login).
# The default gcloud config (~/.config/gcloud, the work/university login) is never read or changed.
set -euo pipefail

export CLOUDSDK_CONFIG="$HOME/.config/gcloud-aisb"
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

GCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$GCP_DIR/../.." && pwd)"
PROJECT_FILE="$GCP_DIR/project.env"

REGION=us-east1
ZONE=us-east1-b
AGENT_VM=ms-agent
RELAY_VM=ms-relay
WAKER=ms-waker
KILLSWITCH=ms-killswitch
TOPIC=billing-alerts
REPO=ms
BUDGET_NAME="aisb-mainstreet 200 USD cap"
IAP_RANGE=35.235.240.0/20

say() { printf '[gcp] %s\n' "$*"; }
warn() { printf '[gcp] WARNING: %s\n' "$*" >&2; }
die() { printf '[gcp] ERROR: %s\n' "$*" >&2; exit 1; }

# Refuse to run against anything but the personal login in ~/.config/gcloud-aisb.
guard_account() {
  command -v gcloud >/dev/null || die "gcloud is not installed"
  local acct
  acct="$(gcloud config get account 2>/dev/null || true)"
  [[ -n $acct ]] || die "no account in $CLOUDSDK_CONFIG. Log in with: CLOUDSDK_CONFIG=$CLOUDSDK_CONFIG gcloud auth login"
  [[ $acct != *@umd.edu ]] || die "refusing to run as $acct (a umd.edu account). Use the personal login in $CLOUDSDK_CONFIG."
  ACCOUNT=$acct
}

load_project() {
  [[ -f $PROJECT_FILE ]] || die "$PROJECT_FILE is missing; run deploy/gcp/setup.sh first"
  # shellcheck disable=SC1090
  source "$PROJECT_FILE"
  [[ -n ${PROJECT_ID:-} ]] || die "PROJECT_ID is not set in $PROJECT_FILE"
  export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
}

retry() { # retry N CMD...: IAM and new APIs take a while to propagate
  local n=$1 i
  shift
  for ((i = 1; i <= n; i++)); do
    "$@" >/dev/null 2>&1 && return 0
    ((i == n)) && break
    sleep 10
  done
  "$@" >/dev/null # last try, with its error shown
}

vm_status() { gcloud compute instances describe "$1" --zone "$ZONE" --format='value(status)' 2>/dev/null || echo MISSING; }

vm_ssh() { # vm_ssh VM COMMAND: run COMMAND on VM over IAP
  local vm=$1
  shift
  gcloud compute ssh "$vm" --zone "$ZONE" --tunnel-through-iap --quiet --command "$*" -- \
    -o ConnectTimeout=25 -o ServerAliveInterval=15 -o LogLevel=ERROR
}

vm_scp() { # vm_scp LOCAL VM REMOTE
  gcloud compute scp "$1" "$2:$3" --zone "$ZONE" --tunnel-through-iap --quiet --scp-flag=-q
}

# Start VM if it is stopped, then wait until it is RUNNING and answers SSH over IAP.
ensure_running() {
  local vm=$1 st i
  for ((i = 0; i < 60; i++)); do
    st="$(vm_status "$vm")"
    case $st in
      RUNNING) break ;;
      TERMINATED | STOPPED) say "$vm is $st; starting it"; gcloud compute instances start "$vm" --zone "$ZONE" --async >/dev/null ;;
      MISSING) die "$vm does not exist; run deploy/gcp/setup.sh" ;;
      *) ;;
    esac
    sleep 5
  done
  [[ $(vm_status "$vm") == RUNNING ]] || die "$vm did not reach RUNNING"
  wait_bootstrap_serial "$vm"
  for ((i = 0; i < 30; i++)); do
    vm_ssh "$vm" true >/dev/null 2>&1 && return 0
    sleep 6
  done
  die "$vm is RUNNING but SSH over IAP does not answer"
}

# Wait for the startup-script's "done" (guest attribute mainstreet/bootstrap, else the serial console) without
# SSH: the first SSH login creates the caller's user, and on ms-agent that must not happen before mainstreet
# takes uid 1000.
wait_bootstrap_serial() {
  local vm=$1 i out
  for ((i = 0; i < 80; i++)); do
    out="$(gcloud compute instances get-guest-attributes "$vm" --zone "$ZONE" --query-path=mainstreet/bootstrap \
      --format='value(value)' 2>/dev/null || true)"
    [[ -n $out ]] || out="$(gcloud compute instances get-serial-port-output "$vm" --zone "$ZONE" 2>/dev/null |
      grep -Eo 'mainstreet-bootstrap: (done|FAILED)' | tail -1 || true)"
    [[ $out == *done ]] && return 0
    [[ $out == *FAILED ]] && die "$vm's startup-script failed; see: gcloud compute instances get-serial-port-output $vm --zone $ZONE"
    ((i == 0)) && say "waiting for $vm's startup-script (serial console)"
    sleep 8
  done
  die "$vm's startup-script did not finish in 10 min"
}

wait_bootstrap() { # wait_bootstrap VM: the startup-script installs packages once; up to 10 min
  local vm=$1 i
  for ((i = 0; i < 60; i++)); do
    vm_ssh "$vm" 'test -f /var/lib/mainstreet/bootstrap.done' >/dev/null 2>&1 && return 0
    ((i == 0)) && say "waiting for $vm's startup-script to finish (sudo journalctl -u google-startup-scripts on the VM)"
    sleep 10
  done
  die "$vm's bootstrap did not finish in 10 min"
}
