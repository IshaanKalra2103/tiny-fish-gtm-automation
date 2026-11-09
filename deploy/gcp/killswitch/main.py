"""Kill switch: a budget notification with costAmount >= budgetAmount disables billing on this project.

Google's "disable billing with budget notifications" pattern (Cloud Run functions 2nd gen, Pub/Sub trigger).
Removing the project's billing account stops every paid resource in it (VMs, Cloud Run, the function itself).
The function's service account holds roles/billing.projectManager on this project only, which is enough to
unlink it; it has no rights on the billing account or on any other project.
"""
import base64
import json
import logging
import os

import functions_framework

log = logging.getLogger("killswitch")
logging.basicConfig(level=logging.INFO)


def over_budget(payload: dict) -> bool:
    return float(payload["costAmount"]) >= float(payload["budgetAmount"])


def handle(payload: dict, client, project_id: str | None) -> str:
    """Decide and act on one budget notification. `client` is a billing_v1.CloudBillingClient (or a fake)."""
    try:
        cost, budget = float(payload["costAmount"]), float(payload["budgetAmount"])
    except (KeyError, TypeError, ValueError):
        log.warning("not a budget notification: %s", str(payload)[:300])
        return "ignored: not a budget notification"
    if not over_budget(payload):
        return f"no action: cost {cost:.2f} < budget {budget:.2f}"
    if not project_id:
        log.error("over budget but TARGET_PROJECT is not set")
        return "error: no project"
    name = f"projects/{project_id}"
    try:
        enabled = client.get_project_billing_info(name=name).billing_enabled
    except Exception as e:  # noqa: BLE001 - if in doubt, assume billing is on and disable it
        log.warning("could not read billing info (%s); assuming billing is enabled", e)
        enabled = True
    if not enabled:
        return "no action: billing already disabled"
    client.update_project_billing_info(request={"name": name, "project_billing_info": {"billing_account_name": ""}})
    log.warning("cost %.2f >= budget %.2f: billing DISABLED on %s", cost, budget, project_id)
    return f"billing disabled on {project_id}"


def decode(cloud_event_data: dict) -> dict:
    return json.loads(base64.b64decode(cloud_event_data["message"]["data"]).decode("utf-8"))


@functions_framework.cloud_event
def stop_billing(cloud_event):
    from google.cloud import billing_v1

    result = handle(decode(cloud_event.data), billing_v1.CloudBillingClient(), os.environ.get("TARGET_PROJECT"))
    log.info(result)
    return result
