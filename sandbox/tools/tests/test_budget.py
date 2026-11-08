import pytest

from mstools.budget import BudgetExceeded, bump_count, charge, spent


def test_charge_accumulates(tmp_path):
    led = tmp_path / "b.json"
    charge(led, "tinyfish_owner", 0.40, 1.50)
    charge(led, "tinyfish_owner", 0.60, 1.50)
    assert spent(led, "tinyfish_owner") == pytest.approx(1.00)


def test_charge_over_cap_raises_and_does_not_write(tmp_path):
    led = tmp_path / "b.json"
    charge(led, "tinyfish_owner", 1.00, 1.50)
    with pytest.raises(BudgetExceeded):
        charge(led, "tinyfish_owner", 0.60, 1.50)
    assert spent(led, "tinyfish_owner") == pytest.approx(1.00)


def test_bump_count_per_day_limit(tmp_path):
    led = tmp_path / "b.json"
    bump_count(led, "previews", 2, per_day=True)
    bump_count(led, "previews", 2, per_day=True)
    with pytest.raises(BudgetExceeded):
        bump_count(led, "previews", 2, per_day=True)
