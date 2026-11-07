"""The LLM provider interface (section 3.5). Swapping providers is one file.

A provider only speaks a wire format: it sends one prompt with an output schema and
returns the raw text. Building the prompt, validating the output, retrying once and
falling back all happen once, in services/, never inside a provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ...schemas import Passage


@dataclass(frozen=True)
class Prompt:
    system: str                       # the instructions: the only trusted text
    user: str                         # evidence, conversation and question, all as data
    schema: dict[str, Any]            # JSON schema the output must follow
    temperature: float
    # The same evidence as structured data, for the stub provider and for tests.
    passages: list[Passage] = field(default_factory=list)
    question: str = ""
    # Seconds this one call may take, set by services/ from the request budget. None
    # means the provider's own LLM_TIMEOUT_SECONDS.
    timeout: float | None = None


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLMProvider(Protocol):
    name: str

    def complete(self, prompt: Prompt) -> Completion:
        """One call to the model. May raise on a timeout or an HTTP error."""
        ...
