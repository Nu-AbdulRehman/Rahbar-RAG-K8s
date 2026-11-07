"""The retriever interface. The rest of the API only ever sees this."""

from __future__ import annotations

from typing import Any, Protocol

from ..schemas import Passage


class Retriever(Protocol):
    name: str

    def retrieve(self, question: str, k: int, include_superseded: bool = False) -> list[Passage]:
        """Return up to k passages, best first. Superseded documents are left out unless
        include_superseded is True (section 3.2 step 4)."""
        ...

    def count(self) -> int:
        """Chunks in the index; raises if the store or the collection is unreachable."""
        ...

    def pin(self) -> dict[str, Any] | None:
        """The embedding pin the indexer recorded ({"embed_model", "dimension"}), or None
        for a retriever with no index behind it (section 4.4)."""
        return None
