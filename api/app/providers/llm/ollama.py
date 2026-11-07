"""Ollama provider: ollama-host or ollama-incluster (section 3.5).

POST {ollama_url}/api/chat with the output JSON schema as `format`, which Ollama
enforces while decoding. The reply is still validated by the service.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from .base import Completion, Prompt


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.url = f"{settings.ollama_url.rstrip('/')}/api/chat"
        self.client = client or httpx.Client(timeout=settings.llm_timeout)

    def complete(self, prompt: Prompt) -> Completion:
        response = self.client.post(self.url, json={
            "model": self.settings.llm_model,
            "messages": [{"role": "system", "content": prompt.system},
                         {"role": "user", "content": prompt.user}],
            "format": prompt.schema,
            "stream": False,
            "options": {"temperature": prompt.temperature},
        })
        response.raise_for_status()
        body = response.json()
        return Completion(text=body.get("message", {}).get("content", ""),
                          tokens_in=int(body.get("prompt_eval_count") or 0),
                          tokens_out=int(body.get("eval_count") or 0))
