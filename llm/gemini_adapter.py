"""
llm/gemini_adapter.py — Google Gemini / OpenRouter adapter.

Supports two modes:
  1. OpenRouter (key starts with 'sk-or-v1-'): uses OpenAI-compatible httpx call
     to https://openrouter.ai/api/v1/chat/completions with model 'google/gemini-2.0-flash'
  2. Native Google AI Studio: uses google-generativeai SDK

Supports text + base64 image (multimodal).
Raises ProviderError on any API failure.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Optional

import httpx

import config
from llm.gateway import LLMResponse, ProviderError

logger = logging.getLogger(__name__)

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
# Use the env-configured model ID as the OpenRouter model
_OPENROUTER_GEMINI_MODEL = config.GEMINI_MODEL_ID  # e.g. google/gemini-2.5-flash


class GeminiAdapter:
    """Adapter for Google Gemini — works via OpenRouter or native Google AI SDK."""

    MODEL_ID = config.GEMINI_MODEL_ID

    def _is_openrouter_key(self) -> bool:
        return config.GEMINI_API_KEY.startswith("sk-or-v1-")

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.2,
        image_b64: Optional[str] = None,
    ) -> LLMResponse:
        if not config.has_gemini_credentials():
            raise ProviderError("Gemini credentials not configured (GEMINI_API_KEY missing)")

        if self._is_openrouter_key():
            return self._complete_openrouter(messages, tools, temperature, image_b64)
        else:
            return self._complete_native(messages, tools, temperature, image_b64)

    # ------------------------------------------------------------------
    # OpenRouter path
    # ------------------------------------------------------------------

    def _complete_openrouter(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        temperature: float,
        image_b64: Optional[str],
    ) -> LLMResponse:
        start = time.monotonic()
        try:
            payload_messages = list(messages)

            # Inject image into last user message if provided
            if image_b64:
                for i in range(len(payload_messages) - 1, -1, -1):
                    if payload_messages[i].get("role") == "user":
                        payload_messages[i] = {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": payload_messages[i].get("content", "")},
                                {"type": "image_url",
                                 "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                            ],
                        }
                        break

            payload: dict = {
                "model": _OPENROUTER_GEMINI_MODEL,
                "messages": payload_messages,
                "temperature": temperature,
                "max_tokens": 1024,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            headers = {
                "Authorization": f"Bearer {config.GEMINI_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://hec-early-warning.local",
                "X-Title": "HEC Early Warning System",
            }

            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{_OPENROUTER_BASE}/chat/completions",
                    json=payload,
                    headers=headers,
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
                model_id=_OPENROUTER_GEMINI_MODEL,
                route_used="openrouter_gemini",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(elapsed_ms, 2),
                cost_usd=_estimate_cost_gemini(tokens_in, tokens_out),
            )
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"OpenRouter Gemini HTTP {e.response.status_code}: {e.response.text[:300]}") from e
        except Exception as e:
            raise ProviderError(f"OpenRouter Gemini failed: {e}") from e

    # ------------------------------------------------------------------
    # Native Google AI Studio path
    # ------------------------------------------------------------------

    def _complete_native(
        self,
        messages: list[dict],
        tools: Optional[list[dict]],
        temperature: float,
        image_b64: Optional[str],
    ) -> LLMResponse:
        start = time.monotonic()
        try:
            import google.generativeai as genai
            genai.configure(api_key=config.GEMINI_API_KEY)
            model = genai.GenerativeModel(self.MODEL_ID)

            system_text = ""
            body_parts: list = []
            for msg in messages:
                if msg.get("role") == "system":
                    system_text = msg.get("content", "")
                else:
                    body_parts.append(msg.get("content", ""))

            full_text = (f"{system_text}\n\n" if system_text else "") + "\n".join(body_parts)
            content_parts: list = [full_text]

            if image_b64:
                try:
                    image_bytes = base64.b64decode(image_b64)
                    content_parts.append({"mime_type": "image/jpeg", "data": image_bytes})
                except Exception:
                    pass

            gen_config = genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=1024,
            )
            response = model.generate_content(content_parts, generation_config=gen_config)
            elapsed_ms = (time.monotonic() - start) * 1000

            result_text = response.text if hasattr(response, "text") else str(response)
            usage = getattr(response, "usage_metadata", None)
            tokens_in = getattr(usage, "prompt_token_count", 0) if usage else 0
            tokens_out = getattr(usage, "candidates_token_count", 0) if usage else 0

            return LLMResponse(
                content=result_text,
                model_id=self.MODEL_ID,
                route_used="gemini_direct",
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=round(elapsed_ms, 2),
                cost_usd=_estimate_cost_gemini(tokens_in, tokens_out),
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"GeminiAdapter (native) failed: {e}") from e


def _estimate_cost_gemini(tokens_in: int, tokens_out: int) -> float:
    return round((tokens_in / 1_000_000) * 0.075 + (tokens_out / 1_000_000) * 0.30, 6)
