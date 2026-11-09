#!/usr/bin/env bash
# MainStreet AI go-live (plan Task 15): API, public tunnel, Vercel deploy, iMessage relay.
#
#   scripts/live.sh [start] [--no-deploy] [--no-relay]
#   scripts/live.sh status     what is running, plus health
#   scripts/live.sh stop       stop everything this script started
#
# start:
#   1. caffeinate -dimsu in the background
#   2. keys from the macOS Keychain (never printed): TINYFISH_API_KEY, OPENROUTER_API_KEY,
#      AGENTMAIL_API_KEY, and AISB_CLAUDE_OAUTH as CLAUDE_CODE_OAUTH_TOKEN
#   3. a fresh MS_RELAY_SECRET for this run, shared by the API and the relay
#   4. colima + the mainstreet-sandbox image, then the API (uv run msapi) on 127.0.0.1:$MS_API_PORT
#   5. cloudflared quick tunnel to the API; its trycloudflare.com URL is the public agent URL
#   6. unless --no-deploy: Vercel production env NEXT_PUBLIC_AGENT_API_URL = tunnel URL, then deploy
#   7. unless --no-relay: the iMessage relay (imessage/, npm start) against the local API
#   8. waits for <tunnel>/api/health to say ok
#
# State lives in scripts/.live/ (gitignored): pids ("name pid" per line), tunnel_url, *.log.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIVE="$ROOT/scripts/.live"
PIDS="$LIVE/pids"
TUNNEL_FILE="$LIVE/tunnel_url"
PORT="${MS_API_PORT:-8787}"
WEB_URL="https://mainstreet-ai-five.vercel.app"
IMAGE="${MS_SANDBOX_IMAGE:-mainstreet-sandbox}"
VERCEL_VAR="NEXT_PUBLIC_AGENT_API_URL"
DOH="https://1.1.1.1/dns-query"
# env flags that drop the API's keys from processes that don't need them (tunnel, relay, vercel).
NO_KEYS=(-u TINYFISH_API_KEY -u OPENROUTER_API_KEY -u AGENTMAIL_API_KEY -u CLAUDE_CODE_OAUTH_TOKEN)
STARTED=0

say() { printf '[live] %s\n' "$*"; }
warn() { printf '[live] WARNING: %s\n' "$*" >&2; }
die() {
  printf '[live] ERROR: %s\n' "$*" >&2
  if [[ $STARTED == 1 ]]; then
    say "stopping what this run started"
    do_stop >/dev/null 2>&1 || true
  fi
  exit 1
}

usage() { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; }

# ---- process bookkeeping -------------------------------------------------------------------

# What each recorded process must look like, so a stale pid file never kills an unrelated process.
pattern_for() {
  case $1 in
    caffeinate) echo 'caffeinate' ;;
    api) echo 'msapi' ;;
    tunnel) echo 'cloudflared' ;;
    relay) echo 'npm|node|tsx' ;;
    *) echo '^$' ;;
  esac
}

alive() { # alive NAME PID
  local cmd
  kill -0 "$2" 2>/dev/null || return 1
  cmd="$(ps -p "$2" -o command= 2>/dev/null)" || return 1
  grep -Eq "$(pattern_for "$1")" <<<"$cmd"
}

descendants() { # every child, grandchild, ... of PID (deepest first)
  local c
  for c in $(pgrep -P "$1" 2>/dev/null); do
    descendants "$c"
    echo "$c"
  done
}

kill_tree() { # kill_tree PID: TERM the process and its children, KILL whatever is left after 5 s
  local all p _
  all="$(descendants "$1") $1"
  # shellcheck disable=SC2086 # word splitting is intended: a list of pids
  kill -TERM $all 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    for p in $all; do kill -0 "$p" 2>/dev/null && break; p=""; done
    [[ -z $p ]] && return 0
    sleep 0.5
  done
  # shellcheck disable=SC2086
  kill -KILL $all 2>/dev/null || true
}

record() { printf '%s %s\n' "$1" "$2" >>"$PIDS"; }

launch() { # launch NAME DIR LOG CMD... : run CMD in DIR in the background, log to LOG, record the pid
  local name=$1 dir=$2 log=$3
  shift 3
  # exec keeps the recorded pid equal to the real process, not a wrapper shell.
  # shellcheck disable=SC2016 # $1/$@ belong to the inner bash
  nohup bash -c 'cd "$1" && shift && exec "$@"' _ "$dir" "$@" >>"$log" 2>&1 </dev/null &
  record "$name" "$!"
}

# Run a command without any of this run's secrets in its environment.
without_secrets() { env "${NO_KEYS[@]}" -u MS_RELAY_SECRET "$@"; }

any_alive() {
  local name pid
  [[ -f $PIDS ]] || return 1
  while read -r name pid; do
    [[ -n ${pid:-} ]] && alive "$name" "$pid" && return 0
  done <"$PIDS"
  return 1
}

# ---- health --------------------------------------------------------------------------------

# Public URLs resolve over DoH so a brand-new trycloudflare name never hits a cached NXDOMAIN.
get_public() { curl -fsS -m 8 --doh-url "$DOH" "$1" 2>/dev/null || curl -fsS -m 8 "$1" 2>/dev/null; }
get_local() { curl -fsS -m 3 "$1" 2>/dev/null; }

field() { # field NAME JSON: true/false for a boolean field, or "?" when absent
  local v
  v="$(grep -Eo "\"$1\": ?(true|false)" <<<"$2" | grep -Eo 'true|false' | head -1 || true)"
  echo "${v:-?}"
}

explain_health() { # explain_health JSON
  local d t
  d="$(field docker "$1")"
  t="$(field token "$1")"
  say "health: ok=$(field ok "$1") docker=$d token=$t"
  [[ $d == false ]] && warn "docker=false: is colima running, and does 'docker image inspect $IMAGE' succeed? Build it with: docker build -t $IMAGE sandbox/"
  [[ $t == false ]] && warn "token=false: Keychain item AISB_CLAUDE_OAUTH is not a Claude Code OAuth token (expected sk-ant-oat..., from 'claude setup-token')"
  return 0
}

# ---- stop / status -------------------------------------------------------------------------

do_stop() {
  local name pid lines stopped=0
  if [[ ! -f $PIDS ]]; then
    say "nothing recorded in scripts/.live/pids; nothing to stop"
    rm -f "$TUNNEL_FILE"
    return 0
  fi
  # Newest first: relay, tunnel, api, caffeinate.
  lines="$(tail -r "$PIDS" 2>/dev/null || cat "$PIDS")"
  while read -r name pid; do
    [[ -n ${pid:-} ]] || continue
    if alive "$name" "$pid"; then
      kill_tree "$pid"
      say "stopped $name (pid $pid)"
      stopped=$((stopped + 1))
    else
      say "$name (pid $pid) was not running"
    fi
  done <<<"$lines"
  rm -f "$PIDS" "$TUNNEL_FILE"
  say "stopped $stopped process(es). The site now shows its offline banner; demos still work."
}

do_status() {
  local name pid tunnel body
  if [[ -f $PIDS ]]; then
    while read -r name pid; do
      [[ -n ${pid:-} ]] || continue
      if alive "$name" "$pid"; then say "$name: running (pid $pid)"; else say "$name: NOT running (pid $pid)"; fi
    done <"$PIDS"
  else
    say "no processes recorded (scripts/.live/pids missing)"
  fi
  if body="$(get_local "http://127.0.0.1:$PORT/api/health")"; then
    say "local API http://127.0.0.1:$PORT: $body"
  else
    say "local API http://127.0.0.1:$PORT: not answering"
  fi
  tunnel="$(cat "$TUNNEL_FILE" 2>/dev/null || true)"
  if [[ -n $tunnel ]]; then
    if body="$(get_public "$tunnel/api/health")"; then
      say "tunnel $tunnel: $body"
      explain_health "$body"
    else
      say "tunnel $tunnel: not answering"
    fi
  else
    say "tunnel: none recorded"
  fi
  say "site: $WEB_URL"
}

# ---- start ---------------------------------------------------------------------------------

keychain_export() { # keychain_export ITEM VAR: export VAR from Keychain item ITEM without echoing it
  local val
  if ! val="$(security find-generic-password -s "$1" -w 2>/dev/null)" || [[ -z $val ]]; then
    die "Keychain item '$1' is missing or empty. Add it with: security add-generic-password -U -a \"\$USER\" -s $1 -w"
  fi
  export "$2=$val"
}

wait_for() { # wait_for SECONDS CMD...: retry CMD every second until it succeeds
  local n=$1 i
  shift
  for ((i = 0; i < n; i++)); do
    "$@" && return 0
    sleep 1
  done
  return 1
}

relay_deps_load() {
  (cd "$ROOT/imessage" && node --input-type=module -e 'await import("spectrum-ts"); await import("@spectrum-ts/imessage")') >/dev/null 2>&1
}

tunnel_url_from_log() {
  grep -Eo 'https://[-a-z0-9]+\.trycloudflare\.com' "$LIVE/tunnel.log" 2>/dev/null | grep -v '^https://api\.' | head -1
}

do_start() {
  local deploy=$1 relay=$2 tunnel body pids_in_use deploy_url="" deploy_failed=0

  # Preflight: nothing is started until all of this passes.
  mkdir -p "$LIVE"
  if any_alive; then
    die "already running (see 'scripts/live.sh status'). Run 'scripts/live.sh stop' first."
  fi
  rm -f "$PIDS" "$TUNNEL_FILE"
  local t
  for t in uv curl openssl colima docker security caffeinate; do
    command -v "$t" >/dev/null || die "'$t' is not installed"
  done
  if ! command -v cloudflared >/dev/null; then
    say "installing cloudflared with brew"
    brew install cloudflared || die "could not install cloudflared"
  fi
  if [[ $deploy == 1 ]]; then
    command -v vercel >/dev/null || die "'vercel' is not installed (or pass --no-deploy)"
    [[ -f $ROOT/web/.vercel/project.json ]] || die "web/ is not linked to Vercel (cd web && vercel link), or pass --no-deploy"
  fi
  if [[ $relay == 1 ]]; then
    command -v npm >/dev/null || die "'npm' is not installed (or pass --no-relay)"
    if ! grep -q '^PROJECT_ID=.' "$ROOT/imessage/.env" 2>/dev/null || ! grep -q '^PROJECT_SECRET=.' "$ROOT/imessage/.env" 2>/dev/null; then
      die "imessage/.env needs PROJECT_ID and PROJECT_SECRET (Photon dashboard), or pass --no-relay"
    fi
    # node_modules can be present but damaged, so check that the Photon SDK actually loads.
    if ! relay_deps_load; then
      say "imessage/node_modules is missing or broken; reinstalling (npm ci)"
      if ! (cd "$ROOT/imessage" && npm ci --no-audit --no-fund >>"$LIVE/relay.log" 2>&1) || ! relay_deps_load; then
        die "the relay's dependencies do not load; see scripts/.live/relay.log"
      fi
    fi
  fi
  pids_in_use="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true)"
  [[ -z $pids_in_use ]] || die "port $PORT is already in use by pid(s) $pids_in_use"

  keychain_export TINYFISH_API_KEY TINYFISH_API_KEY
  keychain_export OPENROUTER_API_KEY OPENROUTER_API_KEY
  keychain_export AGENTMAIL_API_KEY AGENTMAIL_API_KEY
  keychain_export AISB_CLAUDE_OAUTH CLAUDE_CODE_OAUTH_TOKEN
  say "keys loaded from the Keychain"

  unset MS_RUNNER # a leftover MS_RUNNER=fake from testing would serve the fake agent
  MS_RELAY_SECRET="$(openssl rand -hex 16)"
  export MS_RELAY_SECRET MS_API_PORT="$PORT" MS_WEB_URL="$WEB_URL"
  export MS_WEB_ORIGINS="$WEB_URL,http://localhost:3000"

  if ! colima status >/dev/null 2>&1; then
    say "starting colima"
    colima start || die "colima did not start"
  fi
  docker info >/dev/null 2>&1 || die "docker is not answering (colima status?)"
  docker image inspect "$IMAGE" >/dev/null 2>&1 || die "docker image '$IMAGE' is missing. Build it with: docker build -t $IMAGE sandbox/"
  local running
  running="$(docker ps --format '{{.Names}}' 2>/dev/null || true)"
  if [[ $relay == 1 ]] && grep -qx gtm-paperclip <<<"$running"; then
    die "gtm-paperclip is running and also answers the Photon line. Stop it (docker stop gtm-paperclip) or pass --no-relay"
  fi

  # From here on, a failure stops whatever was started.
  STARTED=1
  launch caffeinate "$ROOT" "$LIVE/caffeinate.log" caffeinate -dimsu
  say "caffeinate on"

  launch api "$ROOT" "$LIVE/api.log" uv run msapi
  say "API starting on 127.0.0.1:$PORT (log: scripts/.live/api.log)"
  wait_for 90 get_local "http://127.0.0.1:$PORT/api/health" >/dev/null ||
    die "the API did not answer on port $PORT within 90 s; see scripts/.live/api.log"
  say "API up"

  # 127.0.0.1 rather than localhost: the API binds IPv4 only.
  launch tunnel "$ROOT" "$LIVE/tunnel.log" env "${NO_KEYS[@]}" -u MS_RELAY_SECRET \
    cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT"
  wait_for 60 tunnel_url_from_log >/dev/null || die "no trycloudflare.com URL in scripts/.live/tunnel.log within 60 s"
  tunnel="$(tunnel_url_from_log)"
  printf '%s\n' "$tunnel" >"$TUNNEL_FILE"
  say "tunnel: $tunnel"
  wait_for 60 grep -q 'Registered tunnel connection' "$LIVE/tunnel.log" || warn "cloudflared has not reported a registered connection yet"
  wait_for 90 get_public "$tunnel/api/health" >/dev/null ||
    die "the tunnel did not reach the API within 90 s; see scripts/.live/tunnel.log"
  say "tunnel reaches the API"

  if [[ $deploy == 1 ]]; then
    say "pointing Vercel production $VERCEL_VAR at the tunnel and deploying (log: scripts/.live/deploy.log)"
    (
      cd "$ROOT/web"
      without_secrets vercel env rm "$VERCEL_VAR" production --yes >>"$LIVE/deploy.log" 2>&1 || true
      printf %s "$tunnel" | without_secrets vercel env add "$VERCEL_VAR" production --yes --force >>"$LIVE/deploy.log" 2>&1
    ) || {
      deploy_failed=1
      warn "could not set $VERCEL_VAR on Vercel; see scripts/.live/deploy.log"
    }
    if [[ $deploy_failed == 0 ]]; then
      if deploy_url="$(cd "$ROOT/web" && without_secrets vercel deploy --prod --yes 2>>"$LIVE/deploy.log" | tail -1)" && [[ $deploy_url == https://* ]]; then
        say "deployed: $deploy_url (production alias $WEB_URL)"
      else
        deploy_failed=1
        warn "vercel deploy failed; see scripts/.live/deploy.log. The env var is set, so retry with: (cd web && vercel deploy --prod --yes)"
      fi
    fi
  else
    say "--no-deploy: Vercel untouched. The site only reaches this agent if $VERCEL_VAR already equals $tunnel"
  fi

  if [[ $relay == 1 ]]; then
    # The relay keeps MS_RELAY_SECRET (it signs its calls) but not the API's keys.
    launch relay "$ROOT/imessage" "$LIVE/relay.log" env "${NO_KEYS[@]}" AGENT_API_URL="http://127.0.0.1:$PORT" npm start
    if wait_for 30 grep -q '\[relay\] listening' "$LIVE/relay.log"; then
      say "iMessage relay listening (log: scripts/.live/relay.log)"
    else
      die "the iMessage relay did not start within 30 s; see scripts/.live/relay.log"
    fi
  else
    say "--no-relay: iMessage relay not started"
  fi

  say "waiting for $tunnel/api/health to report ok"
  local i ok=0
  body=""
  for ((i = 0; i < 45; i++)); do
    body="$(get_public "$tunnel/api/health" || true)"
    if [[ $(field ok "$body") == true ]]; then
      ok=1
      break
    fi
    sleep 2
  done

  echo
  say "production: $WEB_URL${deploy_url:+ (this deploy: $deploy_url)}"
  say "tunnel:     $tunnel"
  if [[ $ok == 1 ]]; then
    say "health ok"
  else
    explain_health "$body"
    warn "health is not ok yet; processes are left running. Check 'scripts/live.sh status'."
  fi
  say "stop with: scripts/live.sh stop"
  [[ $ok == 1 && $deploy_failed == 0 ]]
}

# ---- main ----------------------------------------------------------------------------------

main() {
  local cmd=start deploy=1 relay=1 a
  for a in "$@"; do
    case $a in
      start | stop | status) cmd=$a ;;
      --no-deploy) deploy=0 ;;
      --no-relay) relay=0 ;;
      -h | --help) usage; exit 0 ;;
      *) usage >&2; die "unknown argument: $a" ;;
    esac
  done
  case $cmd in
    start) do_start "$deploy" "$relay" ;;
    stop) do_stop ;;
    status) do_status ;;
  esac
}

main "$@"
