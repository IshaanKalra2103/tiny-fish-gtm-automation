from mscatalog import store
from mscatalog.queries import query_grid


def test_query_grid_includes_hvac_receptionist():
    qs = query_grid(store.load_needs())
    assert any("receptionist" in q and "HVAC" in q for q in qs)


def test_query_grid_count():
    needs = store.load_needs()
    expected = sum(2 * len(jobs) for jobs in needs["type_needs"].values()) + 9
    qs = query_grid(needs)
    assert len(qs) == expected
    assert sum(1 for q in qs if q.startswith("site:theresanaiforthat.com")) == 9
