"""
llm/groq_adapter.py — Groq direct adapter.

Uses the groq Python SDK for fast inference.
Raises ProviderError on any API failure.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import config
from llm.gateway import LLMResponse, ProviderError

logger = logging.getLogger(__name__)


class GroqAdapter:
    """Direct adapter for Groq (llama-3.3-70b-versatile or similar)."""

    MODEL_ID = config.GROQ_MODEL_ID

    def __init__(self) -> None:
        self._client = None  # lazy init

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not config.has_groq_credentials():
            raise ProviderError("Groq credentials not configured (GROQ_API_KEY missing)")
        try:
            from groq import Groq
            self._client = Groq(api_key=config.GROQ_API_KEY)
            return self._client
        except Exception as e:
            raise ProviderError(f"GroqAdapter init failed: {e}") from e

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
    ) -> LLMResponse:
        """Call Groq and return an LLMResponse."""
        start = time.monotonic()
        try:
            client = self._get_client()

            kwargs: dict = {
                "model": self.MODEL_ID,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 1024,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000

            choice = response.choices[0]
            result_text = choice.message.content or ""

            usage = response.usage
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0

            return LLMResponse(
                content=result_text,
                model_id=self.MODEL_ID,
                route_used="groq_direct",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(elapsed_ms, 2),
                cost_usd=_estimate_cost_groq(tokens_in, tokens_out),
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"GroqAdapter.complete failed: {e}") from e


def _estimate_cost_groq(tokens_in: int, tokens_out: int) -> float:
    """Rough Groq pricing estimate for llama-3.3-70b (USD per 1M tokens)."""
    # llama-3.3-70b on Groq: ~$0.59/1M input, $0.79/1M output
    return round((tokens_in / 1_000_000) * 0.59 + (tokens_out / 1_000_000) * 0.79, 6)
