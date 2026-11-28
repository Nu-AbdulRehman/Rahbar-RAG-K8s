"""RAGOps A2: the data lake moves documents, never deletes them, and can roll back."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.lake import ARCHIVE, QUARANTINE, RAW, Lake, version_key


def _md(folder: Path, name: str, doc_id: str, version: str, body: str = "Text.") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(f"---\ndoc_id: {doc_id}\ndoc_version: {version}\n---\n"
                               f"# {doc_id}\n{body}\n", encoding="utf-8")


def _lake(tmp_path: Path) -> Lake:
    return Lake(str(tmp_path / "lake"), str(tmp_path / "raw"))


def test_versions_sort_by_their_numbers() -> None:
    assert version_key("2023-08") < version_key("2026") < version_key("2026-06")
    assert version_key("unknown") < version_key("2019-20")


def test_refresh_adds_new_documents_and_drops_deleted_ones(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _md(lake.raw, "a.md", "a", "1")
    _md(lake.raw, "b.md", "b", "1")
    assert sorted(lake.refresh()["added"]) == ["a.md", "b.md"]
    (lake.raw / "b.md").unlink()
    assert lake.refresh() == {"added": [], "deleted": ["b.md"]}
    assert [e.file for e in lake.current()] == ["a.md"]


def test_intake_moves_a_batch_from_incoming_into_raw(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _md(lake.incoming, "new.md", "new", "2027")
    assert lake.intake() == ["new.md"]
    assert (lake.raw / "new.md").exists() and not (lake.incoming / "new.md").exists()


def test_quarantine_moves_the_file_with_a_reason_and_forgets_it(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _md(lake.raw, "bad.md", "bad", "1")
    lake.refresh()
    entry = lake.current()[0]
    assert lake.quarantine(entry, ["only 2 words extracted"], "run1") == "moved"
    assert (lake.quarantine_dir / "bad.md").exists() and not (lake.raw / "bad.md").exists()
    reason = json.loads((lake.quarantine_dir / "bad.md.reason.json").read_text())
    assert reason["reasons"] == ["only 2 words extracted"]
    assert lake.current() == []
    assert [e.location for e in lake.catalog()] == [QUARANTINE]
    lake.refresh()                             # a quarantined file is not picked up again
    assert lake.current() == []


def test_archive_then_restore_swaps_the_current_version(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    _md(lake.raw, "rules-2023.md", "rules", "2023")
    _md(lake.raw, "rules-2026.md", "rules", "2026")
    lake.refresh()
    old = next(e for e in lake.current() if e.doc_version == "2023")
    lake.archive(old)
    assert (lake.archive_dir / "rules" / "2023" / "rules-2023.md").exists()
    archived = next(e for e in lake.catalog() if e.location == ARCHIVE)
    assert archived.superseded is True and archived.doc_version == "2023"

    back, displaced = lake.restore("rules", "2023")
    assert back.location == RAW and back.superseded is False
    assert [e.doc_version for e in displaced] == ["2026"]
    assert (lake.raw / "rules-2023.md").exists()
    assert (lake.archive_dir / "rules" / "2026" / "rules-2026.md").exists()
    current = {e.doc_version: e.superseded for e in lake.current()}
    assert current == {"2023": False, "2026": True}


def test_a_read_only_source_is_copied_not_lost(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lake = _lake(tmp_path)
    _md(lake.raw, "fixture.md", "f", "1")
    lake.refresh()

    def refuse(src: str, dst: str) -> None:
        raise PermissionError("read-only file system")

    monkeypatch.setattr("shutil.move", refuse)
    assert lake.archive(lake.current()[0]) == "copied (source is read-only)"
    assert (lake.raw / "fixture.md").exists()
    assert (lake.archive_dir / "f" / "1" / "fixture.md").exists()


def test_a_batch_beside_a_fetch_index_is_still_catalogued(tmp_path: Path) -> None:
    """raw/ holds fetch.py's _index.json; a batch moved in by intake() is not in it, and
    must still be read from its front matter (the first Batch B run indexed none of it)."""
    lake = _lake(tmp_path)
    lake.raw.mkdir(parents=True)
    (lake.raw / "fees.html").write_text("<html></html>", encoding="utf-8")
    (lake.raw / "_index.json").write_text(json.dumps(
        [{"file": "fees.html", "doc_id": "fees", "title": "Fees", "doc_version": "2026"}]),
        encoding="utf-8")
    (lake.raw / "MANIFEST.md").write_text("| file | sha256 |", encoding="utf-8")  # fetch.py's
    _md(lake.incoming, "library.md", "library", "2026")
    lake.intake()
    lake.refresh()
    assert sorted(e.file for e in lake.current()) == ["fees.html", "library.md"]
