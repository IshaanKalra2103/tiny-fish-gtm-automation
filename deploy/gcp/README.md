# MainStreet AI on Google Cloud

This folder runs the MainStreet AI agent stack on GCP. It is the same stack the Mac runs (`scripts/live.sh`), on a VM
that sleeps when nobody is using it, behind a public Cloud Run URL that wakes it up.

All scripts use the gcloud config dir `~/.config/gcloud-aisb` (the personal Google login). They refuse to run if
that config has no account or the account ends in `@umd.edu`. The default `~/.config/gcloud` is never touched.

## What exists

Project and location: see `project.env` (written by `setup.sh`). Region `us-east1`, zone `us-east1-b`.

| Resource | What it is |
|---|---|
| `ms-agent` | VM, e2-standard-2, Debian 12, 30 GB pd-balanced. Docker, uv, the `mainstreet-sandbox` image, and `msapi` as a systemd unit on 0.0.0.0:8787. Stops itself when idle. |
| `ms-waker` | Cloud Run service, the public API URL (`WAKER_URL` in `project.env`). Proxies every request to `ms-agent:8787` and starts the VM when it is stopped. min 0, max 2 instances, 900 s timeout, Direct VPC egress (private ranges only). |
| `ms-relay` | VM, e2-micro (free tier), Debian 12, Node 22. The iMessage relay (`imessage/`) as the systemd unit `ms-relay`, installed disabled. |
| `ms-killswitch` | Cloud Run function (2nd gen) on the Pub/Sub topic `billing-alerts`. Disables billing on this project when the budget is used up. |
| Budget | `aisb-mainstreet 200 USD cap` on the billing account, scoped to this project, cumulative since 2026-11-01 (not monthly), credits excluded, alerts at 50/90/100%, notifications to `billing-alerts`. |
| Firewall | `ms-allow-iap-ssh` (22 from 35.235.240.0/20, IAP only), `ms-allow-waker-8787` (8787 from the default us-east1 subnet only), `ms-deny-other-ingress` (everything else denied for both VMs). The default 0.0.0.0/0 SSH/RDP/ICMP rules are deleted. |
| Service accounts | `ms-agent-vm` and `ms-relay-vm` (read their own secrets), `ms-waker` (custom role with only `compute.instances.get` and `compute.instances.start`, bound on `ms-agent` alone), `ms-killswitch` (Project Billing Manager on this project only). |
| Artifact Registry | `ms` (docker) for the waker image. |

## Commands

Run from the repo root.

```sh
deploy/gcp/setup.sh                     # create or update everything (idempotent)
deploy/gcp/setup.sh --refresh-secrets   # also upload new versions of the keys from the Keychain / imessage/.env
deploy/gcp/push.sh                      # ship HEAD to ms-agent (starts it if stopped)
deploy/gcp/push.sh relay                # ship HEAD's imessage/ to ms-relay (unit stays as it is)
deploy/gcp/ctl.sh status                # billing, VM states, waker URL; does not wake anything
deploy/gcp/ctl.sh health                # GET <waker>/api/health (this wakes ms-agent)
deploy/gcp/ctl.sh start | stop          # start or stop ms-agent by hand
deploy/gcp/ctl.sh ssh [relay]           # shell on a VM through IAP
deploy/gcp/ctl.sh logs [relay]          # msapi + idle timer logs, or relay logs
deploy/gcp/ctl.sh relay-on | relay-off  # start or stop the iMessage relay (cutover)
deploy/gcp/ctl.sh teardown --yes        # delete the budget and the whole project
uv run --no-project deploy/gcp/smoke.py # health, POST /api/owners, one turn polled to done, with timings
```

`push.sh` ships only what is committed: it runs `git archive HEAD`, copies the tarball over IAP, syncs it into
`/opt/mainstreet` (keeping `workspaces/`, `budget/` and `.venv/`), runs `uv sync`, `docker build -t mainstreet-sandbox
sandbox/`, restarts `msapi` and waits for its health check. Rerun it after new commits or a new catalog export.

## How idle-stop and wake work

On `ms-agent`, the timer `ms-idle.timer` runs `ms-idle.sh` every 2 minutes. It powers the VM off when all of these
hold: no container labelled `mainstreet=1` is running, nothing under `workspaces/*/turns` or
`workspaces/*/messages.jsonl` changed in the last 20 minutes, the VM has been up more than 15 minutes, and no
`push.sh` deploy is in progress. A stopped VM costs only its disk.

`ms-waker` caches the VM status for 10 s. When a request arrives and the VM is stopped, it calls the Compute API to
start it and holds the request until `GET :8787/api/health` answers (at most 150 s), then proxies it. Concurrent
requests share one wake. `GET /api/health` never waits: while the VM is waking it answers
`{"ok": true, "docker": true, "token": true, "waking": true}` at once, so the site does not show its offline banner.
Response bodies are streamed (SSE and the poll route work). The waker passes headers through (Origin,
X-Relay-Secret, ...) and sets `CF-Connecting-IP` to the last `X-Forwarded-For` hop, the client address Cloud Run
appended, overwriting anything the client sent, because the API rate-limits per client on it.

Measured on 2026-11-08: from a stopped VM, the waking health answer came back in 1 s, the API answered 56 s after
the start, and a first turn finished 90 s after the first request (a warm turn took 28 s).

The iMessage relay calls the waker URL. A cold start (about 60 s) plus a turn can exceed the relay's 300 s timeout
(`imessage/src/relay.ts` `TIMEOUT_MS`). The unit sets `RELAY_TIMEOUT_MS=420000`, but `imessage/src/index.ts` does not
read it yet: it needs `timeoutMs: Number(process.env.RELAY_TIMEOUT_MS) || undefined` in the `handleMessage` deps.

## Where secrets live

In Secret Manager in this project, uploaded by `setup.sh` through a pipe (never printed):

| Secret | Source |
|---|---|
| `claude-code-oauth-token` | Keychain `AISB_CLAUDE_OAUTH` (env `CLAUDE_CODE_OAUTH_TOKEN`) |
| `tinyfish-api-key`, `openrouter-api-key`, `agentmail-api-key` | Keychain items of the same names in capitals |
| `ms-relay-secret` | generated once by `setup.sh`; shared by the API and the relay |
| `photon-project-id`, `photon-project-secret` | `imessage/.env` (`PROJECT_ID`, `PROJECT_SECRET`) |

At each start, the unit's `ExecStartPre` runs `fetch-secrets.py` as root. It reads the secrets with the VM's service
account (metadata server token, no key files) and writes a mode 600 env file: `/etc/mainstreet/agent.env` (root) on
`ms-agent`, `/opt/ms-relay/imessage/.env` (user `msrelay`) on `ms-relay`. To rotate a key: update the Keychain, run
`setup.sh --refresh-secrets`, then restart the unit (`push.sh`, or `sudo systemctl restart msapi` on the VM).

## Kill switch

The budget sends a Pub/Sub message to `billing-alerts` several times a day. `ms-killswitch` reads `costAmount` and
`budgetAmount`; when `costAmount >= budgetAmount` (200 USD) it removes the billing account from this project, which
stops every paid resource in it, including the VMs, the waker and the function itself. It cannot touch the billing
account or any other project. Credits are excluded from the budget, so free-trial credit use counts toward the 200 USD.
Email alerts go to the billing account admins at 50%, 90% and 100%.

Budget data lags actual usage by hours, so spend can pass 200 USD by a little before billing is cut. To turn things back
on after a cut: link billing again in the console (or `gcloud billing projects link`), then start the VMs.

Logic tests (sample payloads under and over budget, fake billing client):

```sh
(cd deploy/gcp/killswitch && uv run pytest -q)
(cd deploy/gcp/waker && uv run pytest -q)
```

## Cutover from the Mac

1. Stop the Mac relay (`scripts/live.sh stop`, or at least its relay).
2. `deploy/gcp/ctl.sh relay-on` starts `ms-relay` on GCP.
3. Point Vercel's `NEXT_PUBLIC_AGENT_API_URL` (production) at `WAKER_URL` and redeploy the web.

Owner workspaces created on the Mac stay on the Mac; the VM starts with its own empty `workspaces/`.
