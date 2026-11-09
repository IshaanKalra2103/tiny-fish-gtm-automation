import pytest


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MS_CATALOG_DATA", str(tmp_path / "data"))
    return tmp_path / "data"
