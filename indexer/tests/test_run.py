"""The whole run on a copy of the fixture corpus with fakes for Ollama, Chroma and Redis
(§3.1, §3.3, RAGOps A1): verify, chunk, sync, and invalidate the cache last."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from pipeline import run
from pipeline.store import SyncResult

FIXTURES = Path(__file__).resolve().parents[2] / "eval" / "fixtures"


def _copy_fixtures(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    shutil.copytree(FIXTURES, raw)          # never run the pipeline on the repo's own files
    return raw


def _fake_sync(events: list[str], stored: dict[str, Any]) -> Any:
    def fake(chunks: list, settings: Any, embed_texts: Any, client: Any = None) -> SyncResult:
        events.append("sync")
        stored["chunks"] = chunks
        return SyncResult(len(chunks), 0, 0, 0, len(chunks), False)
    return fake


def test_full_run_verifies_then_syncs_then_invalidates_the_cache(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_data_lake: Path) -> None:
    events: list[str] = []
    stored: dict[str, Any] = {}
    monkeypatch.setenv("CORPUS_DIR", str(_copy_fixtures(tmp_path)))
    monkeypatch.setattr("pipeline.store.sync", _fake_sync(events, stored))
    monkeypatch.setattr(run, "invalidate_cache", lambda s: events.append("invalidate") or 7)
    monkeypatch.setattr("sys.argv", ["pipeline.run"])

    assert run.main() == 0
    assert events == ["sync", "invalidate"]
    by_source = {}
    for c in stored["chunks"]:
        by_source.setdefault(c.source, set()).add(c.superseded)
    assert set(by_source) == {"academic-rules-2023.md", "academic-rules-2026.md", "fees-2026.md"}
    assert by_source["academic-rules-2023.md"] == {True}    # the older version, still indexed

    reports = list((isolated_data_lake / "reports").glob("verify-*.json"))
    assert len(reports) == 1
    actions = {d["file"]: d["action"] for d in json.loads(reports[0].read_text())["documents"]}
    assert actions == {"academic-rules-2023.md": "archive", "academic-rules-2026.md": "index",
                       "fees-2026.md": "index"}
    assert (isolated_data_lake / "archive" / "academic-rules" / "2023"
            / "academic-rules-2023.md").exists()


def test_an_empty_document_is_quarantined_and_the_rest_indexed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_data_lake: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "rules.md").write_text("---\ndoc_version: 2026\n---\n# 1. Rules\n"
                                  + "Students attend every lecture. " * 10, encoding="utf-8")
    (raw / "blank.md").write_text("", encoding="utf-8")       # e.g. a scan without OCR
    stored: dict[str, Any] = {}
    monkeypatch.setenv("CORPUS_DIR", str(raw))
    monkeypatch.setattr("pipeline.store.sync", _fake_sync([], stored))
    monkeypatch.setattr(run, "invalidate_cache", lambda s: 1)
    monkeypatch.setattr("sys.argv", ["pipeline.run"])

    assert run.main() == 0
    assert {c.source for c in stored["chunks"]} == {"rules.md"}
    assert (isolated_data_lake / "quarantine" / "blank.md").exists()
    assert not (raw / "blank.md").exists()                     # moved, not copied
    reason = json.loads((isolated_data_lake / "quarantine" / "blank.md.reason.json").read_text())
    assert any("words extracted" in r for r in reason["reasons"])


def test_a_redis_failure_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def down(settings: Any) -> int:
        raise ConnectionError("redis unreachable")

    monkeypatch.setattr("pipeline.dummy.write_dummy_index", lambda s, c: 3)
    monkeypatch.setattr("pipeline.store.get_client", lambda s: None)
    monkeypatch.setattr(run, "invalidate_cache", down)
    monkeypatch.setattr("sys.argv", ["pipeline.run", "--dummy"])
    with pytest.raises(ConnectionError):
        run.main()


def test_invalidate_bumps_the_shared_generation_key() -> None:
    from pipeline.config import get_settings
    from pipeline.invalidate import GENERATION_KEY, invalidate_cache

    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, int] = {}

        def incr(self, key: str) -> int:
            self.values[key] = self.values.get(key, 0) + 1
            return self.values[key]

    fake = FakeRedis()
    assert invalidate_cache(get_settings(), fake) == 1
    assert invalidate_cache(get_settings(), fake) == 2
    assert GENERATION_KEY == "rahbar:cache:generation"


def test_a_rollback_survives_the_next_ingestion(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_data_lake: Path) -> None:
    """Restoring an older version archives the newer one; the next run must keep the
    restored version current, not re-archive it because a newer version exists."""
    from pipeline.config import get_settings
    from pipeline.lake import Lake

    raw = tmp_path / "raw"
    raw.mkdir()
    body = "Tuition is charged per credit hour for every course a student takes. " * 4
    for name, version in (("fees-2026.md", "2026"), ("fees-2027.md", "2027")):
        (raw / name).write_text(f"---\ndoc_id: fees\ndoc_version: {version}\n---\n"
                                f"# Fees {version}\n{body}\n", encoding="utf-8")
    stored: dict[str, Any] = {}
    monkeypatch.setenv("CORPUS_DIR", str(raw))
    monkeypatch.setattr("pipeline.store.sync", _fake_sync([], stored))
    monkeypatch.setattr(run, "invalidate_cache", lambda s: 1)
    monkeypatch.setattr("sys.argv", ["pipeline.run"])

    assert run.main() == 0                           # 2026 archived, 2027 current
    Lake(get_settings().data_lake_dir, str(raw)).restore("fees", "2026")
    assert run.main() == 0
    superseded = {c.source: c.superseded for c in stored["chunks"]}
    assert superseded == {"fees-2026.md": False, "fees-2027.md": True}
