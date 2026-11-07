"""The retriever interface. The rest of the API only ever sees this."""

from __future__ import annotations

from typing import Protocol

from ..schemas import Passage


class Retriever(Protocol):
    name: str

    def retrieve(self, question: str, k: int, include_superseded: bool = False) -> list[Passage]:
        """Return up to k passages, best first. Superseded documents are left out unless
        include_superseded is True (section 3.2 step 4)."""
        ...
