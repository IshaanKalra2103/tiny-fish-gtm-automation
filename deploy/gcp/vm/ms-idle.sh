#!/bin/bash
# Power the agent VM off when it is idle. Run every 2 minutes by ms-idle.timer. It stops only when ALL hold:
#   - no container labelled mainstreet=1 is running (no agent turn in progress)
#   - nothing under workspaces/*/turns or workspaces/*/messages.jsonl changed in the last 20 minutes
#   - the VM has been up for more than 15 minutes
#   - push.sh is not deploying (it touches /run/ms-idle-hold)
# A guest poweroff leaves the instance TERMINATED (no VM charge); ms-waker starts it again on the next request.
set -u
WS=${MS_WORKSPACES:-/opt/mainstreet/workspaces}
IDLE_MIN=${MS_IDLE_MINUTES:-20}
MIN_UPTIME=${MS_MIN_UPTIME_SECONDS:-900}
HOLD=/run/ms-idle-hold

stay() { echo "staying up: $*"; exit 0; }

up=$(cut -d. -f1 /proc/uptime)
((up > MIN_UPTIME)) || stay "uptime ${up}s is not over ${MIN_UPTIME}s"
running=$(docker ps -q --filter label=mainstreet=1 2>/dev/null || true)
[[ -z $running ]] || stay "agent container(s) running: $(echo "$running" | wc -l)"
if [[ -d $WS ]]; then
  recent=$(find "$WS" -mindepth 2 -maxdepth 5 \( -path "$WS/*/turns" -o -path "$WS/*/turns/*" -o -path "$WS/*/messages.jsonl" \) \
    -mmin "-$IDLE_MIN" -print -quit 2>/dev/null)
  [[ -z $recent ]] || stay "turn activity in the last $IDLE_MIN min"
fi
if [[ -e $HOLD ]] && [[ -n $(find "$HOLD" -mmin "-$IDLE_MIN" 2>/dev/null) ]]; then
  stay "deploy hold ($HOLD) is fresh"
fi
echo "idle: no agent containers, no turn activity for $IDLE_MIN min, up ${up}s; powering off"
systemctl poweroff
