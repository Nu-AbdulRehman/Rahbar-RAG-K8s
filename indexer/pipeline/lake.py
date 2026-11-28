"""The data lake (RAGOps A1, A2; paper 4.2.1-4.2.4).

    <DATA_LAKE_DIR>/
      catalog.json  every document the lake knows, and where it is: raw, archive, quarantine
      incoming/     a new batch lands here; intake() moves it into raw/
      raw/          current documents (CORPUS_DIR, which may live outside the lake)
      archive/      superseded versions: archive/<doc_id>/<doc_version>/<file>
      quarantine/   documents that failed verification, each with <file>.reason.json
      reports/      verify-<run>.json and ingest-<run>.json, one per run

The catalog lives in the lake, not in raw/, because raw/ can be read-only (in CI it is the
fixture folder baked into the image). A document is never deleted, only moved; a move the
file system refuses falls back to a copy, and the report says so.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Any

INDEX = "_index.json"              # written by corpus/fetch.py next to the files
DOC_SUFFIXES = {".pdf", ".md", ".html", ".htm", ".txt"}
RAW, ARCHIVE, QUARANTINE = "raw", "archive", "quarantine"


@dataclass
class Entry:
    """One document version in the catalog."""

    file: str
    doc_id: str
    title: str
    doc_version: str
    superseded: bool
    location: str = RAW
    extra: dict[str, Any] = field(default_factory=dict)   # url, sha256, ... from fetch.py

    def record(self) -> dict[str, Any]:
        out = {**self.extra, **asdict(self)}
        out.pop("extra")
        return out


def version_key(version: str) -> tuple[int, ...]:
    """'2023-08' < '2026' < '2026-06'; a version without digits sorts first."""
    return tuple(int(n) for n in re.findall(r"\d+", version)) or (-1,)


def _front_matter(path: Path) -> dict[str, str]:
    """`key: value` lines between leading '---' markers (the CI fixtures, Batch B)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta


def _first_heading(path: Path) -> str:
    """A Markdown document's title is its first '# ' heading when the front matter has
    none; the title is still in the document, so completeness can see it."""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _entry(record: dict[str, Any]) -> Entry:
    file = str(record["file"])
    superseded = record.get("superseded", False)
    if isinstance(superseded, str):
        superseded = superseded.strip().lower() == "true"
    known = {"file", "doc_id", "title", "name", "doc_version", "superseded", "location"}
    return Entry(file=file, doc_id=str(record.get("doc_id") or Path(file).stem),
                 title=str(record.get("title") or record.get("name") or ""),
                 doc_version=str(record.get("doc_version") or ""),
                 superseded=bool(superseded), location=str(record.get("location") or RAW),
                 extra={k: v for k, v in record.items() if k not in known})


def read_folder(folder: Path) -> list[Entry]:
    """What a folder of documents says about itself: its _index.json when present
    (fetch.py), otherwise each Markdown file's front matter. Missing fields stay empty,
    for the completeness check to report."""
    index = folder / INDEX
    entries = [_entry(r) for r in json.loads(index.read_text(encoding="utf-8"))] \
        if index.exists() else []
    listed = {e.file for e in entries}
    # Documents the index does not list (a batch moved in by intake()) still count, from
    # their front matter: found on the first Batch B run, which indexed none of them.
    for path in sorted(folder.glob("*")) if folder.is_dir() else []:
        if path.suffix.lower() not in DOC_SUFFIXES or path.name in listed \
                or path.name.lower().startswith(("readme", "manifest")):   # not documents
            continue
        meta = _front_matter(path) if path.suffix.lower() == ".md" else {}
        if path.suffix.lower() == ".md" and not meta.get("title"):
            meta["title"] = _first_heading(path)
        entries.append(_entry({"file": path.name, **meta}))
    return entries


class Lake:
    def __init__(self, root: str, raw: str | None = None) -> None:
        self.root = Path(root)
        self.raw = Path(raw) if raw else self.root / RAW
        self.incoming = self.root / "incoming"
        self.archive_dir = self.root / ARCHIVE
        self.quarantine_dir = self.root / QUARANTINE
        self.reports = self.root / "reports"
        self.catalog_path = self.root / "catalog.json"

    def lock(self) -> IO[bytes]:
        """Hold the lake for one ingestion run: a second run (a Job started while the
        CronJob's run is going) waits here instead of reading catalog.json half-written or
        a file the first run is moving. Found on the cluster, where two overlapping runs
        failed with JSONDecodeError and FileNotFoundError. Released when the returned file
        is closed or the process ends, so a crashed run never leaves a stale lock.

        ponytail: flock is enforced on node-local storage (the ReadWriteOnce lake PVC); on an
        NFS-backed ReadWriteMany volume shared across nodes, use a Kubernetes Lease instead."""
        self.root.mkdir(parents=True, exist_ok=True)
        handle = open(self.root / ".lock", "a+b")       # noqa: SIM115 - the caller holds it
        if sys.platform == "win32":                      # local runs on Windows
            import msvcrt
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:                          # LK_LOCK gives up after ~10 s
                    continue
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    # --- catalog -----------------------------------------------------------------------
    def catalog(self) -> list[Entry]:
        if not self.catalog_path.exists():
            return []
        return [_entry(r) for r in json.loads(self.catalog_path.read_text(encoding="utf-8"))]

    def save(self, entries: list[Entry]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog_path.write_text(json.dumps([e.record() for e in entries], indent=2),
                                     encoding="utf-8")

    def path(self, entry: Entry) -> Path:
        if entry.location == ARCHIVE:
            return self.archive_dir / entry.doc_id / entry.doc_version / entry.file
        if entry.location == QUARANTINE:
            return self.quarantine_dir / entry.file
        return self.raw / entry.file

    def refresh(self) -> dict[str, list[str]]:
        """Bring the catalog in line with raw/: add documents seen for the first time,
        update the metadata of current ones, and drop current ones whose file is gone (a
        deleted document; its chunks are pruned by the store step). Archived and
        quarantined versions are the lake's own state and are kept."""
        known = {(e.file, e.location): e for e in self.catalog()}
        seen = {e.file: e for e in read_folder(self.raw)}
        handled = {f for f, loc in known if loc != RAW}
        added, deleted = [], []
        entries = [e for (f, loc), e in known.items() if loc != RAW]
        for file, e in seen.items():
            if file in handled:
                continue                      # archived or quarantined; a copy may linger
            if (file, RAW) not in known:
                added.append(file)
            entries.append(e)
        for (file, loc) in known:
            if loc == RAW and file not in seen:
                deleted.append(file)
        self.save(entries)
        return {"added": added, "deleted": deleted}

    def current(self) -> list[Entry]:
        """Every version that is indexed: raw/ and archive/, never quarantine/."""
        return [e for e in self.catalog() if e.location in (RAW, ARCHIVE)]

    def _replace(self, old: Entry, new: Entry | None) -> None:
        entries = [e for e in self.catalog() if (e.file, e.location) != (old.file, old.location)]
        self.save(entries + ([new] if new else []))

    # --- moves -------------------------------------------------------------------------
    @staticmethod
    def _move(src: Path, dst: Path) -> str:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dst))
            return "moved"
        except OSError:                       # a read-only source, e.g. the CI fixtures
            shutil.copy2(src, dst)
            return "copied (source is read-only)"

    def intake(self) -> list[str]:
        """Move a new batch from incoming/ into raw/ (the data lake update step). Its
        _index.json, if any, is merged into raw's; front matter needs no merge."""
        batch = read_folder(self.incoming)
        for e in batch:
            self._move(self.incoming / e.file, self.raw / e.file)
        incoming_index = self.incoming / INDEX
        if incoming_index.exists():
            raw_index = self.raw / INDEX
            merged = {r["file"]: r for r in (json.loads(raw_index.read_text(encoding="utf-8"))
                                             if raw_index.exists() else [])}
            merged.update({e.file: e.record() for e in batch})
            raw_index.write_text(json.dumps(list(merged.values()), indent=2), encoding="utf-8")
            incoming_index.unlink()
        return [e.file for e in batch]

    def quarantine(self, entry: Entry, reasons: list[str], run_id: str) -> str:
        """Take a failed document out of the index: move it beside a reason file. The
        catalog remembers it, so the next run does not pick it up again."""
        moved = Entry(**{**asdict(entry), "location": QUARANTINE})
        how = self._move(self.path(entry), self.path(moved))
        (self.quarantine_dir / f"{entry.file}.reason.json").write_text(json.dumps(
            {"run": run_id, "entry": entry.record(), "reasons": reasons}, indent=2),
            encoding="utf-8")
        self._replace(entry, moved)
        return how

    def archive(self, entry: Entry) -> str:
        """Move a superseded version into archive/<doc_id>/<version>/. It stays indexed,
        with superseded: true, and restore() brings it back (A2)."""
        if entry.location == ARCHIVE:
            return "already archived"
        moved = Entry(**{**asdict(entry), "superseded": True, "location": ARCHIVE})
        how = self._move(self.path(entry), self.path(moved))
        self._replace(entry, moved)
        return how

    def restore(self, doc_id: str, version: str) -> tuple[Entry, list[Entry]]:
        """Roll back: make <doc_id> <version> current again and archive the version(s)
        that were current. The next ingestion run flips the superseded metadata only; the
        text is unchanged, so nothing is re-embedded."""
        wanted = next((e for e in self.catalog() if e.location == ARCHIVE
                       and e.doc_id == doc_id and e.doc_version == version), None)
        if wanted is None:
            have = sorted((e.doc_id, e.doc_version) for e in self.catalog()
                          if e.location == ARCHIVE)
            raise SystemExit(f"no archived version {version!r} of {doc_id!r}; archived: {have}")
        displaced = [e for e in self.catalog() if e.location == RAW and e.doc_id == doc_id]
        for e in displaced:
            self.archive(e)
        back = Entry(**{**asdict(wanted), "superseded": False, "location": RAW})
        self._move(self.path(wanted), self.path(back))
        self._replace(wanted, back)
        return back, displaced

    def write_report(self, name: str, body: dict[str, Any]) -> Path:
        self.reports.mkdir(parents=True, exist_ok=True)
        path = self.reports / name
        path.write_text(json.dumps(body, indent=2), encoding="utf-8")
        return path
