"""The embedding pin (section 4.4): the api refuses to serve an index built with another
embedding model, or with vectors of another dimension.

The indexer writes {"embed_model", "dimension"} into the collection metadata
(indexer/pipeline/store.py, pin_metadata). This module compares that record with the
api's own EMBED_MODEL and with the length of the vectors its embedder returns. Any
difference keeps the pod not ready, with a message naming both values. There is no
fallback: never re-embed here, never ignore the dimension, never pick one of the two.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import Settings

log = logging.getLogger("rahbar.pin")


def pin_conflict(pin: dict[str, Any] | None, settings: Settings,
                 dimension: int | None) -> str | None:
    """None when the pin matches; otherwise what conflicts, naming both values.

    `pin` is None for a retriever without an index (the stub). `dimension` is the length
    of a vector from the api's embedder, or None until it has produced one."""
    if pin is None:
        return None
    index_model = pin.get("embed_model")
    if index_model != settings.embed_model:
        return (f"index was embedded with EMBED_MODEL={index_model!r} but the api has "
                f"EMBED_MODEL={settings.embed_model!r}; re-index or fix the ConfigMap")
    index_dim = pin.get("dimension")
    if index_dim is None:
        return "index metadata records no vector dimension; re-index"
    if dimension is not None and int(index_dim) != dimension:
        return (f"index vectors have dimension {index_dim} but {settings.embed_model!r} "
                f"returns dimension {dimension}; re-index")
    return None


def report(conflict: str | None, last: str | None) -> str | None:
    """Log a conflict once when it appears and once when it clears, not on every probe.
    Returns the new `last`."""
    if conflict != last:
        if conflict:
            log.error("embedding pin mismatch", extra={"conflict": conflict})
        else:
            log.info("embedding pin matches")
    return conflict
