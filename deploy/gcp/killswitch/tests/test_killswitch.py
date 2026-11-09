"""Kill-switch logic with sample Pub/Sub budget payloads and a fake billing client. Nothing real is disabled."""
import base64
import json
from types import SimpleNamespace

import pytest

import main


class FakeBilling:
    def __init__(self, enabled=True, fail_get=False):
        self.enabled, self.fail_get = enabled, fail_get
        self.updates = []

    def get_project_billing_info(self, name):
        if self.fail_get:
            raise RuntimeError("permission denied")
        return SimpleNamespace(billing_enabled=self.enabled)

    def update_project_billing_info(self, request):
        self.updates.append(request)


def sample(cost, budget=200.0):
    # Shape of a Cloud Billing budget notification (schemaVersion 1.0).
    return {"budgetDisplayName": "aisb-mainstreet $200 cap", "alertThresholdExceeded": 0.9, "costAmount": cost,
            "costIntervalStart": "2026-11-01T07:00:00Z", "budgetAmount": budget,
            "budgetAmountType": "SPECIFIED_AMOUNT", "currencyCode": "USD"}


def event(payload):
    data = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"message": {"data": data, "attributes": {"billingAccountId": "X", "budgetId": "b", "schemaVersion": "1.0"}},
            "subscription": "projects/p/subscriptions/s"}


@pytest.mark.parametrize("cost", [0, 12.34, 100, 199.99])
def test_under_budget_does_nothing(cost):
    b = FakeBilling()
    assert main.handle(main.decode(event(sample(cost))), b, "aisb-mainstreet-abcd").startswith("no action")
    assert b.updates == []


@pytest.mark.parametrize("cost", [200, 200.01, 512.5])
def test_at_or_over_budget_disables_billing_on_this_project_only(cost):
    b = FakeBilling()
    out = main.handle(main.decode(event(sample(cost))), b, "aisb-mainstreet-abcd")
    assert out == "billing disabled on aisb-mainstreet-abcd"
    assert b.updates == [{"name": "projects/aisb-mainstreet-abcd", "project_billing_info": {"billing_account_name": ""}}]


def test_already_disabled_is_left_alone():
    b = FakeBilling(enabled=False)
    assert "already disabled" in main.handle(sample(250), b, "p")
    assert b.updates == []


def test_unknown_billing_state_still_disables():
    b = FakeBilling(fail_get=True)
    main.handle(sample(250), b, "p")
    assert len(b.updates) == 1


def test_missing_project_does_nothing():
    b = FakeBilling()
    assert main.handle(sample(250), b, None).startswith("error")
    assert b.updates == []


@pytest.mark.parametrize("payload", [{}, {"costAmount": "x", "budgetAmount": 200}, {"budgetAmount": 200}])
def test_malformed_payload_is_ignored(payload):
    b = FakeBilling()
    assert main.handle(payload, b, "p").startswith("ignored")
    assert b.updates == []


def test_entry_point_decodes_cloud_event(monkeypatch):
    b = FakeBilling()
    import google.cloud.billing_v1 as billing_v1

    monkeypatch.setattr(billing_v1, "CloudBillingClient", lambda: b)
    monkeypatch.setenv("TARGET_PROJECT", "aisb-mainstreet-abcd")
    ce = SimpleNamespace(data=event(sample(201)))
    assert main.stop_billing(ce) == "billing disabled on aisb-mainstreet-abcd"
    assert b.updates and b.updates[0]["name"] == "projects/aisb-mainstreet-abcd"
