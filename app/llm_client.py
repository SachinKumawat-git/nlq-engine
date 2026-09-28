"""
LLM abstraction. Two providers implement the same interface so the rest
of the app never knows which one is in use:

  - OllamaClient: local, free, no API key -- the default. Talks to a
    locally-running `ollama serve` over HTTP.
  - OpenAICompatibleClient: any OpenAI-compatible chat/completions
    endpoint (OpenAI, Groq, Together, vLLM, LM Studio, ...). Useful for
    swapping in a hosted model without touching application code.

Both return a raw string; the caller (nl_query.py) is responsible for
parsing/validating the expected JSON shape, since a small local model
will occasionally wrap JSON in prose despite instructions.
"""
from __future__ import annotations
import json
import re
from abc import ABC, abstractmethod

import requests

from app.config import settings


class LLMError(Exception):
    pass


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict:
        """Send a chat request and return a parsed JSON dict."""


def _extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from an LLM response,
    tolerating markdown fences or stray prose around the object."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            text = text[first : last + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"Model did not return valid JSON: {e}. Raw: {text[:500]}")


class OllamaClient(LLMClient):
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model

    def complete_json(self, system: str, user: str) -> dict:
        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise LLMError(
                f"Could not reach Ollama at {self.base_url} (is `ollama serve` "
                f"running and is model '{self.model}' pulled?): {e}"
            )
        content = resp.json().get("message", {}).get("content", "")
        return _extract_json(content)


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model

    def complete_json(self, system: str, user: str) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=settings.llm_timeout_seconds,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise LLMError(f"OpenAI-compatible endpoint request failed: {e}")
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "ollama":
        return OllamaClient()
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleClient()
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
