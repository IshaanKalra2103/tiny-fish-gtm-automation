#!/usr/bin/env bash
# MainStreet AI on GCP: create or update everything (idempotent; safe to rerun).
#
#   deploy/gcp/setup.sh                    create/update the project, VMs, waker, secrets, budget, kill switch
#   deploy/gcp/setup.sh --refresh-secrets  also push new versions of the Keychain keys and Photon credentials
#
# Then deploy the code with deploy/gcp/push.sh (agent) and deploy/gcp/push.sh relay.
# Secrets go from the Keychain (or imessage/.env) straight into Secret Manager through a pipe; none is printed.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

REFRESH=0
for a in "$@"; do
  case $a in
    --refresh-secrets) REFRESH=1 ;;
    -h | --help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $a" ;;
  esac
done

guard_account
say "account: $ACCOUNT (config $CLOUDSDK_CONFIG)"

# ---- 1. project + billing ------------------------------------------------------------------------

if [[ -f $PROJECT_FILE ]]; then
  load_project
else
  BILLING_ACCOUNT="$(gcloud billing accounts list --filter=open=true --format='value(name.basename())' | head -1)"
  [[ -n $BILLING_ACCOUNT ]] || die "no open billing account for $ACCOUNT. Start the free trial at https://console.cloud.google.com/billing, then rerun."
  PROJECT_ID="aisb-mainstreet-$(openssl rand -hex 2)"
  say "creating project $PROJECT_ID"
  gcloud projects create "$PROJECT_ID" --name="MainStreet AI AISB" >/dev/null
  printf 'PROJECT_ID=%s\nBILLING_ACCOUNT=%s\nREGION=%s\nZONE=%s\n' "$PROJECT_ID" "$BILLING_ACCOUNT" "$REGION" "$ZONE" >"$PROJECT_FILE"
  load_project
fi
: "${BILLING_ACCOUNT:?BILLING_ACCOUNT missing in $PROJECT_FILE}"
say "project: $PROJECT_ID  billing account: $BILLING_ACCOUNT"

if [[ $(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)') != True ]]; then
  say "linking billing"
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT" >/dev/null
fi

say "enabling APIs (a minute the first time)"
gcloud services enable compute.googleapis.com run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com pubsub.googleapis.com billingbudgets.googleapis.com \
  cloudbilling.googleapis.com cloudfunctions.googleapis.com eventarc.googleapis.com iam.googleapis.com \
  iap.googleapis.com >/dev/null

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
COMPUTE_SA="$PROJECT_NUMBER-compute@developer.gserviceaccount.com"

# ---- 2. network + firewall -----------------------------------------------------------------------

if ! gcloud compute networks describe default >/dev/null 2>&1; then
  say "creating the default network"
  gcloud compute networks create default --subnet-mode=auto >/dev/null
fi
SUBNET_RANGE="$(gcloud compute networks subnets describe default --region "$REGION" --format='value(ipCidrRange)')"
[[ -n $SUBNET_RANGE ]] || die "no default subnet in $REGION"
say "default subnet $REGION: $SUBNET_RANGE"

fw() { # fw NAME ARGS...: create the rule unless it exists
  local name=$1
  shift
  gcloud compute firewall-rules describe "$name" >/dev/null 2>&1 ||
    gcloud compute firewall-rules create "$name" --network default "$@" >/dev/null
}
fw ms-allow-iap-ssh --direction INGRESS --action ALLOW --rules tcp:22 --source-ranges "$IAP_RANGE" \
  --target-tags ms-agent,ms-relay --priority 900 --description "SSH only through IAP TCP forwarding"
fw ms-allow-waker-8787 --direction INGRESS --action ALLOW --rules tcp:8787 --source-ranges "$SUBNET_RANGE" \
  --target-tags ms-agent --priority 900 --description "agent API only from ms-waker's Direct VPC egress (default subnet)"
fw ms-deny-other-ingress --direction INGRESS --action DENY --rules all --source-ranges 0.0.0.0/0 \
  --target-tags ms-agent,ms-relay --priority 1000 --description "nothing else reaches the MainStreet VMs"
# The auto-created rules that open SSH/RDP/ICMP to 0.0.0.0/0 for every VM in the network: not wanted here.
for r in default-allow-ssh default-allow-rdp default-allow-icmp; do
  if gcloud compute firewall-rules describe "$r" >/dev/null 2>&1; then
    say "deleting firewall rule $r (0.0.0.0/0)"
    gcloud compute firewall-rules delete "$r" --quiet >/dev/null
  fi
done

# ---- 3. service accounts -------------------------------------------------------------------------

sa() { # sa NAME DESCRIPTION -> prints the email
  local email="$1@$PROJECT_ID.iam.gserviceaccount.com"
  gcloud iam service-accounts describe "$email" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$1" --display-name "$2" >/dev/null
  echo "$email"
}
AGENT_SA="$(sa ms-agent-vm "ms-agent VM: reads its secrets")"
RELAY_SA="$(sa ms-relay-vm "ms-relay VM: reads its secrets")"
WAKER_SA="$(sa ms-waker "ms-waker: get/start ms-agent")"
KILL_SA="$(sa ms-killswitch "kill switch: disables billing on this project")"
sleep 5 # new service accounts take a moment to be usable in IAM bindings

proj_bind() { gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$1" --role "$2" --condition=None >/dev/null; }
proj_bind "$AGENT_SA" roles/logging.logWriter
proj_bind "$RELAY_SA" roles/logging.logWriter
proj_bind "$KILL_SA" roles/billing.projectManager # enough to unlink THIS project from billing; nothing else

# ---- 4. secrets ----------------------------------------------------------------------------------

secret_has_version() { [[ -n $(gcloud secrets versions list "$1" --filter=state=ENABLED --limit=1 --format='value(name)' 2>/dev/null) ]]; }
ensure_secret() { gcloud secrets describe "$1" >/dev/null 2>&1 || gcloud secrets create "$1" --replication-policy=automatic >/dev/null; }

# put_secret NAME: reads the value on stdin (never echoed) and adds it as a new version
put_secret() { gcloud secrets versions add "$1" --data-file=- >/dev/null; }

from_keychain() { # from_keychain ITEM SECRET
  ensure_secret "$2"
  if [[ $REFRESH == 1 ]] || ! secret_has_version "$2"; then
    security find-generic-password -s "$1" -w >/dev/null 2>&1 || die "Keychain item $1 is missing"
    security find-generic-password -s "$1" -w 2>/dev/null | tr -d '\r\n' | put_secret "$2"
    say "secret $2: new version from Keychain item $1"
  fi
}
from_keychain AISB_CLAUDE_OAUTH claude-code-oauth-token
from_keychain TINYFISH_API_KEY tinyfish-api-key
from_keychain OPENROUTER_API_KEY openrouter-api-key
from_keychain AGENTMAIL_API_KEY agentmail-api-key

ensure_secret ms-relay-secret
if ! secret_has_version ms-relay-secret; then
  openssl rand -hex 24 | tr -d '\n' | put_secret ms-relay-secret
  say "secret ms-relay-secret: generated"
fi

ENV_FILE="$ROOT/imessage/.env"
from_env_file() { # from_env_file VAR SECRET: the value of VAR in imessage/.env, unquoted, never displayed
  ensure_secret "$2"
  if [[ $REFRESH == 1 ]] || ! secret_has_version "$2"; then
    cut -d= -f1 "$ENV_FILE" | grep -qx "$1" || die "$1 is not in imessage/.env"
    grep -m1 "^$1=" "$ENV_FILE" | cut -d= -f2- | tr -d '\r\n' | sed -E "s/^\"(.*)\"\$/\\1/; s/^'(.*)'\$/\\1/" | put_secret "$2"
    say "secret $2: new version from imessage/.env $1"
  fi
}
[[ -f $ENV_FILE ]] || die "imessage/.env is missing (Photon PROJECT_ID / PROJECT_SECRET)"
from_env_file PROJECT_ID photon-project-id
from_env_file PROJECT_SECRET photon-project-secret

grant_secret() { gcloud secrets add-iam-policy-binding "$1" --member "serviceAccount:$2" --role roles/secretmanager.secretAccessor >/dev/null; }
for s in claude-code-oauth-token tinyfish-api-key openrouter-api-key agentmail-api-key ms-relay-secret; do grant_secret "$s" "$AGENT_SA"; done
for s in photon-project-id photon-project-secret ms-relay-secret; do grant_secret "$s" "$RELAY_SA"; done

# ---- 5. VMs --------------------------------------------------------------------------------------

if [[ $(vm_status "$AGENT_VM") == MISSING ]]; then
  say "creating $AGENT_VM (e2-standard-2, Debian 12, 30 GB pd-balanced)"
  gcloud compute instances create "$AGENT_VM" --zone "$ZONE" --machine-type e2-standard-2 \
    --image-family debian-12 --image-project debian-cloud --boot-disk-size 30GB --boot-disk-type pd-balanced \
    --tags ms-agent --service-account "$AGENT_SA" --scopes cloud-platform \
    --metadata-from-file startup-script="$GCP_DIR/vm/agent-bootstrap.sh" >/dev/null
else
  gcloud compute instances add-metadata "$AGENT_VM" --zone "$ZONE" \
    --metadata-from-file startup-script="$GCP_DIR/vm/agent-bootstrap.sh" >/dev/null
fi
AGENT_IP="$(gcloud compute instances describe "$AGENT_VM" --zone "$ZONE" --format='value(networkInterfaces[0].networkIP)')"
say "$AGENT_VM internal IP: $AGENT_IP"

if [[ $(vm_status "$RELAY_VM") == MISSING ]]; then
  say "creating $RELAY_VM (e2-micro, Debian 12, 10 GB pd-standard)"
  gcloud compute instances create "$RELAY_VM" --zone "$ZONE" --machine-type e2-micro \
    --image-family debian-12 --image-project debian-cloud --boot-disk-size 10GB --boot-disk-type pd-standard \
    --tags ms-relay --service-account "$RELAY_SA" --scopes cloud-platform \
    --metadata-from-file startup-script="$GCP_DIR/vm/relay-bootstrap.sh" >/dev/null
else
  gcloud compute instances add-metadata "$RELAY_VM" --zone "$ZONE" \
    --metadata-from-file startup-script="$GCP_DIR/vm/relay-bootstrap.sh" >/dev/null
fi

# The waker may read and start ms-agent, and nothing else: a custom role bound on that one instance.
ROLE="projects/$PROJECT_ID/roles/msWakerStartGet"
if gcloud iam roles describe msWakerStartGet --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam roles update msWakerStartGet --project "$PROJECT_ID" \
    --permissions compute.instances.get,compute.instances.start >/dev/null
else
  gcloud iam roles create msWakerStartGet --project "$PROJECT_ID" --title "ms-waker: get/start ms-agent" \
    --permissions compute.instances.get,compute.instances.start --stage GA >/dev/null
fi
retry 12 gcloud compute instances add-iam-policy-binding "$AGENT_VM" --zone "$ZONE" \
  --member "serviceAccount:$WAKER_SA" --role "$ROLE" # a new custom role takes a minute to be bindable

# ---- 6. waker (Cloud Run) ------------------------------------------------------------------------

gcloud artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$REPO" --repository-format docker --location "$REGION" >/dev/null
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/$WAKER:$(date +%Y%m%d-%H%M%S)"
say "building $IMAGE with Cloud Build"
gcloud builds submit "$GCP_DIR/waker" --tag "$IMAGE" --quiet >/dev/null

say "deploying Cloud Run service $WAKER"
gcloud run deploy "$WAKER" --image "$IMAGE" --region "$REGION" --service-account "$WAKER_SA" \
  --allow-unauthenticated --min-instances 0 --max-instances 2 --timeout 900 --concurrency 80 \
  --cpu 1 --memory 512Mi --cpu-boost \
  --network default --subnet default --vpc-egress private-ranges-only \
  --set-env-vars "MS_PROJECT=$PROJECT_ID,MS_ZONE=$ZONE,MS_INSTANCE=$AGENT_VM,MS_UPSTREAM_HOST=$AGENT_IP,MS_UPSTREAM_PORT=8787,MS_STATUS_TTL=10,MS_WAKE_TIMEOUT=150" \
  --quiet >/dev/null
WAKER_URL="$(gcloud run services describe "$WAKER" --region "$REGION" --format='value(status.url)')"
say "waker URL: $WAKER_URL"
grep -v '^WAKER_URL=' "$PROJECT_FILE" >"$PROJECT_FILE.tmp" && printf 'WAKER_URL=%s\n' "$WAKER_URL" >>"$PROJECT_FILE.tmp"
mv "$PROJECT_FILE.tmp" "$PROJECT_FILE"

gcloud compute instances add-metadata "$RELAY_VM" --zone "$ZONE" --metadata agent-api-url="$WAKER_URL" >/dev/null

# ---- 7. $200 hard stop: budget -> Pub/Sub -> kill-switch function ----------------------------------

gcloud pubsub topics describe "$TOPIC" >/dev/null 2>&1 || gcloud pubsub topics create "$TOPIC" >/dev/null
gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member serviceAccount:billing-budget-alert@system.gserviceaccount.com --role roles/pubsub.publisher >/dev/null

say "deploying the kill-switch function $KILLSWITCH"
gcloud functions deploy "$KILLSWITCH" --gen2 --region "$REGION" --runtime python312 \
  --source "$GCP_DIR/killswitch" --entry-point stop_billing --trigger-topic "$TOPIC" \
  --service-account "$KILL_SA" --trigger-service-account "$KILL_SA" \
  --set-env-vars "TARGET_PROJECT=$PROJECT_ID" --max-instances 1 --memory 256Mi --no-allow-unauthenticated \
  --quiet >/dev/null
gcloud functions add-invoker-policy-binding "$KILLSWITCH" --region "$REGION" \
  --member "serviceAccount:$KILL_SA" >/dev/null

BUDGET="$(gcloud billing budgets list --billing-account "$BILLING_ACCOUNT" --billing-project "$PROJECT_ID" \
  --format='value(name,displayName)' 2>/dev/null | grep -F "$BUDGET_NAME" | cut -f1 | head -1 || true)"
BUDGET_ARGS=(--budget-amount=200USD --start-date=2026-11-01 --filter-projects="projects/$PROJECT_ID" --credit-types-treatment=exclude-all-credits
  --notifications-rule-pubsub-topic="projects/$PROJECT_ID/topics/$TOPIC" --billing-project "$PROJECT_ID")
if [[ -z $BUDGET ]]; then
  say "creating budget: 200 USD on $PROJECT_ID, alerts at 50/90/100%"
  gcloud billing budgets create --billing-account "$BILLING_ACCOUNT" --display-name "$BUDGET_NAME" "${BUDGET_ARGS[@]}" \
    --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0 >/dev/null
else
  say "budget exists: $BUDGET"
fi

say "setup done"
say "  project:  $PROJECT_ID ($REGION / $ZONE)"
say "  waker:    $WAKER_URL"
say "  VMs:      $AGENT_VM ($(vm_status "$AGENT_VM")), $RELAY_VM ($(vm_status "$RELAY_VM"))"
say "next: deploy/gcp/push.sh && deploy/gcp/push.sh relay"
