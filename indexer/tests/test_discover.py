"""The superseded flag must survive from corpus/raw/_index.json into discover() (§3.1)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.run import discover


def test_discover_reads_versions_from_the_fetch_index(tmp_path: Path) -> None:
    entries = [
        {"file": "old.pdf", "doc_version": "2023-08", "superseded": True},
        {"file": "new.pdf", "doc_version": "2026-06", "superseded": False},
    ]
    (tmp_path / "_index.json").write_text(json.dumps(entries), encoding="utf-8")
    found = {p.name: (version, old) for p, version, old in discover(str(tmp_path))}
    assert found == {"old.pdf": ("2023-08", True), "new.pdf": ("2026-06", False)}
