"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter), OpenAI-compatible.

POST {hosted_base_url}/chat/completions with response_format json_schema. The key comes
from LLM_API_KEY, which only the Secret sets; it is sent as a header and never logged.
"""

from __future__ import annotations

import httpx

from ...config import Settings
from .base import Completion, Prompt


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if not settings.hosted_base_url or not settings.llm_api_key:
            raise ValueError("LLM_PROVIDER=hosted needs HOSTED_BASE_URL and LLM_API_KEY "
                             "(create the Secret with `make secret`)")
        self.settings = settings
        self.url = f"{settings.hosted_base_url.rstrip('/')}/chat/completions"
        self.client = client or httpx.Client(timeout=settings.llm_timeout)

    def complete(self, prompt: Prompt) -> Completion:
        response = self.client.post(
            self.url,
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json={
                "model": self.settings.llm_model,
                "messages": [{"role": "system", "content": prompt.system},
                             {"role": "user", "content": prompt.user}],
                "temperature": prompt.temperature,
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "reply", "schema": prompt.schema}},
            },
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get("usage") or {}
        return Completion(text=body["choices"][0]["message"]["content"] or "",
                          tokens_in=int(usage.get("prompt_tokens") or 0),
                          tokens_out=int(usage.get("completion_tokens") or 0))
