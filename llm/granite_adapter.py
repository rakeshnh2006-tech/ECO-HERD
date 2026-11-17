"""
llm/granite_adapter.py — IBM WatsonX (Granite 4) direct adapter + OpenRouter fallback.

Priority:
  1. IBM WatsonX direct API (ibm-watsonx-ai)
  2. OpenRouter with ibm-granite/granite-4.2-8b (uses same GEMINI_API_KEY/OpenRouter key)

Raises ProviderError on all failures so the gateway can use its own fallback.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import config
from llm.gateway import LLMResponse, ProviderError

logger = logging.getLogger(__name__)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_OPENROUTER_GRANITE_MODEL = "ibm-granite/granite-4.2-8b"


class GraniteAdapter:
    """Direct adapter for IBM WatsonX / Granite 4 with OpenRouter fallback."""

    MODEL_ID = config.GRANITE_MODEL_ID

    def __init__(self) -> None:
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not config.has_ibm_credentials():
            raise ProviderError("IBM credentials not configured")
        try:
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference

            credentials = Credentials(
                url=config.IBM_URL,
                api_key=config.IBM_API_KEY,
            )
            self._client = ModelInference(
                model_id=self.MODEL_ID,
                credentials=credentials,
                project_id=config.IBM_PROJECT_ID,
            )
            return self._client
        except Exception as e:
            raise ProviderError(f"GraniteAdapter WatsonX init failed: {e}") from e

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Try IBM WatsonX first; fall back to OpenRouter if that fails."""
        # Suppress noisy ibm_watsonx_ai 403 log — the 403 is expected (project permission)
        import logging as _logging
        _logging.getLogger("ibm_watsonx_ai").setLevel(_logging.CRITICAL)

        # Try IBM WatsonX
        if config.has_ibm_credentials():
            try:
                return self._complete_watsonx(messages, tools, temperature)
            except ProviderError as e:
                logger.debug("IBM WatsonX unavailable (%s) — using OpenRouter Granite", e)

        # Try OpenRouter with Granite
        if config.GEMINI_API_KEY and config.GEMINI_API_KEY.startswith("sk-or-v1-"):
            try:
                return self._complete_openrouter(messages, tools, temperature)
            except ProviderError as e:
                raise ProviderError(f"Both WatsonX and OpenRouter Granite failed: {e}") from e

        raise ProviderError("No IBM or OpenRouter credentials available for Granite")

    def _complete_watsonx(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        temperature: float,
    ) -> LLMResponse:
        start = time.monotonic()
        try:
            client = self._get_client()
            params = {"max_new_tokens": 2048, "temperature": temperature}
            response = client.chat(messages=messages, params=params)
            elapsed_ms = (time.monotonic() - start) * 1000

            choices = response.get("choices", [{}])
            result_text = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = response.get("usage", {})

            return LLMResponse(
                content=result_text,
                model_id=self.MODEL_ID,
                route_used="ibm_granite_direct",
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                latency_ms=round(elapsed_ms, 2),
                cost_usd=_estimate_cost_granite(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"GraniteAdapter WatsonX call failed: {e}") from e

    def _complete_openrouter(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        temperature: float,
    ) -> LLMResponse:
        import httpx
        start = time.monotonic()
        try:
            payload: dict = {
                "model": _OPENROUTER_GRANITE_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 2048,
            }
            if tools:
                payload["tools"] = tools

            headers = {
                "Authorization": f"Bearer {config.GEMINI_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://hec-early-warning.local",
                "X-Title": "HEC Early Warning System",
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{_OPENROUTER_BASE}/chat/completions",
                    json=payload, headers=headers,
                )
                resp.raise_for_status()

            elapsed_ms = (time.monotonic() - start) * 1000
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            result_text = choice.get("message", {}).get("content", "") or ""
            usage = data.get("usage", {})
            tokens_in = usage.get("prompt_tokens", 0)
            tokens_out = usage.get("completion_tokens", 0)

            return LLMResponse(
                content=result_text,
                model_id=_OPENROUTER_GRANITE_MODEL,
                route_used="openrouter_granite",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(elapsed_ms, 2),
                cost_usd=_estimate_cost_granite(tokens_in, tokens_out),
            )
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"OpenRouter Granite HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except Exception as e:
            raise ProviderError(f"OpenRouter Granite failed: {e}") from e


def _estimate_cost_granite(tokens_in: int, tokens_out: int) -> float:
    return round((tokens_in / 1000) * 0.0006 + (tokens_out / 1000) * 0.0012, 6)
