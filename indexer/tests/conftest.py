"""Every indexer test gets its own data lake. Without this, a test that runs the whole
pipeline on eval/fixtures would move the fixture files into the default lake under /tmp
(verification moves documents; it never deletes them)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_data_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lake = tmp_path / "datalake"
    monkeypatch.setenv("DATA_LAKE_DIR", str(lake))
    return lake
