"""Reading trace records: from the trace volume's JSONL files, or from `kubectl logs`
output (JSON lines whose msg is "trace"). Shared by trace_show and trace_summary."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO


def default_dir() -> str:
    from ..config import get_settings

    return get_settings().trace_dir or "traces"


def from_dir(directory: str) -> Iterator[dict[str, Any]]:
    root = Path(directory)
    if not root.exists():
        raise SystemExit(f"no trace directory {root}: set --dir, or TRACE_DIR")
    for path in sorted(root.rglob("traces-*.jsonl")):
        yield from from_lines(path.open(encoding="utf-8"))


def from_lines(stream: TextIO) -> Iterator[dict[str, Any]]:
    """Trace records in a stream: volume lines are records; log lines are records once
    the logger's own fields are taken off. Anything else is skipped."""
    for line in stream:
        line = line.strip()
        start = line.find("{")             # `kubectl logs --prefix` puts the pod name first
        if start < 0:
            continue
        try:
            entry = json.loads(line[start:])
        except ValueError:
            continue
        if not isinstance(entry, dict) or "trace_id" not in entry:
            continue
        if entry.get("msg") == "trace":
            for key in ("ts", "level", "logger", "msg", "request_id"):
                entry.pop(key, None)
        yield entry


def load(directory: str | None, logs: str | None) -> Iterator[dict[str, Any]]:
    if logs:
        stream = sys.stdin if logs == "-" else open(logs, encoding="utf-8")  # noqa: SIM115
        return from_lines(stream)
    return from_dir(directory or default_dir())
