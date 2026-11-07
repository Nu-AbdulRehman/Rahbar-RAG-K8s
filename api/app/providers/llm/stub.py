"""A provider with no model and no network.

Use it for every unit test and for CI (section 6): tests never call a real model. It is
deterministic: the same prompt always gives the same output. It answers in the JSON the
real models are asked for, so the service validates it exactly like a model's reply.
"""

from __future__ import annotations

import json

from .base import Completion, Prompt


class StubProvider:
    name = "stub"

    def complete(self, prompt: Prompt) -> Completion:
        if "answer" not in prompt.schema.get("properties", {}):
            # The conversation-summary schema (ADR 0002): a deterministic one-liner.
            return Completion(json.dumps({"summary": f"Asked about: {prompt.question}"}))
        reply: dict[str, object]
        if not prompt.passages:
            text = "(stub) No passages were retrieved for this question."
            reply = {"reasoning": "stub: nothing was retrieved",
                     "answer": text,
                     "citations": [], "answered_from_context": False, "confidence": "low"}
        else:
            top = prompt.passages[0]
            text = (f"(stub) A model would answer here from {len(prompt.passages)} passages. "
                    f"The first one says: {top.text}")
            reply = {"reasoning": "stub: cites the first retrieved passage",
                     "answer": text,
                     "citations": [{"source": top.source, "section": top.section,
                                    "page": top.page}],
                     "answered_from_context": True, "confidence": "low"}
        return Completion(json.dumps(reply), tokens_in=len(prompt.user.split()),
                          tokens_out=len(text.split()))
