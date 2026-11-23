from __future__ import annotations

import os
from typing import Protocol

import httpx

from src.config import AppConfig

OPENAI_COMPATIBLE_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
}


class LLMClient(Protocol):
    provider: str
    model: str

    def complete(self, prompt: str) -> str: ...


class OpenAICompatibleClient:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        endpoint: str,
        temperature: float = 0,
        max_tokens: int = 200,
        timeout_seconds: float = 30,
    ):
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self._endpoint = endpoint
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout_seconds

    def complete(self, prompt: str) -> str:
        response = httpx.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()


class ExtractiveClient:
    """No-network fallback for the local demo.

    It is not an LLM: it prepares a deterministic extractive answer body from
    retrieved text so the UI remains demoable without provider credentials.
    """

    provider = "extractive"
    model = "retrieved_context"

    def complete(self, prompt: str) -> str:
        raise RuntimeError("ExtractiveClient does not call a remote model")


def build_llm_client(cfg: AppConfig) -> LLMClient | None:
    """Return a configured client, or None when no usable key is present."""
    provider = str(cfg.llm.get("provider", "")).lower()
    endpoint = OPENAI_COMPATIBLE_ENDPOINTS.get(provider)
    if not endpoint:
        return None

    api_key = os.getenv(f"{provider.upper()}_API_KEY", "").strip()
    if not api_key:
        return None

    return OpenAICompatibleClient(
        provider=provider,
        model=str(cfg.llm.get("model", "")),
        api_key=api_key,
        endpoint=endpoint,
        temperature=float(cfg.llm.get("temperature", 0)),
        max_tokens=int(cfg.llm.get("max_tokens", 200)),
        timeout_seconds=float(cfg.llm.get("timeout_seconds", 30)),
    )
