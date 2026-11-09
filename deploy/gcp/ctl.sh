#!/usr/bin/env bash
# Day-to-day control of the GCP deployment.
#
#   deploy/gcp/ctl.sh status            project, billing, VM states, waker URL (does not wake the VM)
#   deploy/gcp/ctl.sh health            GET <waker>/api/health (wakes ms-agent if it is stopped)
#   deploy/gcp/ctl.sh start | stop      start or stop ms-agent
#   deploy/gcp/ctl.sh ssh [relay]       shell on ms-agent (or ms-relay) over IAP
#   deploy/gcp/ctl.sh logs [relay]      last 100 lines of msapi (or ms-relay) and the idle timer
#   deploy/gcp/ctl.sh relay-on | relay-off   enable+start / stop+disable the iMessage relay (cutover)
#   deploy/gcp/ctl.sh teardown --yes    delete the budget and the whole project (everything in it)
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

cmd=${1:-status}
guard_account
load_project

case $cmd in
  status)
    say "account $ACCOUNT, project $PROJECT_ID ($ZONE)"
    say "billing enabled: $(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')"
    say "$AGENT_VM: $(vm_status "$AGENT_VM")"
    say "$RELAY_VM: $(vm_status "$RELAY_VM")"
    say "waker: ${WAKER_URL:-not deployed}"
    ;;
  health) curl -sS -m 20 "$WAKER_URL/api/health"; echo ;;
  start) gcloud compute instances start "$AGENT_VM" --zone "$ZONE" ;;
  stop) gcloud compute instances stop "$AGENT_VM" --zone "$ZONE" ;;
  ssh)
    vm=$AGENT_VM; [[ ${2:-} == relay ]] && vm=$RELAY_VM
    gcloud compute ssh "$vm" --zone "$ZONE" --tunnel-through-iap
    ;;
  logs)
    if [[ ${2:-} == relay ]]; then
      vm_ssh "$RELAY_VM" 'sudo journalctl -u ms-relay -n 100 --no-pager'
    else
      vm_ssh "$AGENT_VM" 'sudo journalctl -u msapi -n 100 --no-pager; echo; sudo journalctl -u ms-idle -n 10 --no-pager'
    fi
    ;;
  relay-on) vm_ssh "$RELAY_VM" 'sudo systemctl enable --now ms-relay && sleep 5 && sudo journalctl -u ms-relay -n 20 --no-pager' ;;
  relay-off) vm_ssh "$RELAY_VM" 'sudo systemctl disable --now ms-relay; systemctl is-active ms-relay || true' ;;
  teardown)
    [[ ${2:-} == --yes ]] || die "this deletes project $PROJECT_ID and everything in it. Rerun with: ctl.sh teardown --yes"
    for b in $(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" --billing-project "$PROJECT_ID" \
      --format='value(name,displayName)' 2>/dev/null | grep -F "$BUDGET_NAME" | cut -f1); do
      gcloud billing budgets delete "$b" --billing-account "$BILLING_ACCOUNT" --billing-project "$PROJECT_ID" --quiet || true
    done
    gcloud projects delete "$PROJECT_ID" --quiet
    say "project $PROJECT_ID scheduled for deletion (recoverable for 30 days with gcloud projects undelete)"
    ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
