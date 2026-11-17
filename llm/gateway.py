"""
llm/gateway.py — Centralized LLM Gateway.

Routing strategy:
  1. Try OmniRoute (https://omniroute.online/v1) — OpenAI-compatible endpoint.
  2. On OmniRoute failure (ProviderError, HTTP error, timeout):
       fall back to the matching direct provider adapter.
  3. If the direct adapter also fails:
       return a deterministic FALLBACK LLMResponse — NEVER raise or crash.

All calls are logged to MemoryStore for observability.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from pydantic import BaseModel

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models (also imported by adapters)
# ---------------------------------------------------------------------------

class ProviderError(Exception):
    """Raised by provider adapters on API failure. Caught by the gateway."""
    pass


class LLMResponse(BaseModel):
    content: str
    model_id: str = ""
    route_used: str = "none"
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    is_fallback: bool = False


# ---------------------------------------------------------------------------
# Model → adapter mapping
# Populated lazily to avoid circular imports at module load time.
# ---------------------------------------------------------------------------

_MODEL_ADAPTER_CACHE: dict[str, object] = {}


def _get_adapter(model_key: str):
    """Return (and cache) the direct adapter for the given model key."""
    if model_key in _MODEL_ADAPTER_CACHE:
        return _MODEL_ADAPTER_CACHE[model_key]

    if "granite" in model_key.lower() or model_key == config.GRANITE_MODEL_ID:
        from llm.granite_adapter import GraniteAdapter
        adapter = GraniteAdapter()
    elif "gemini" in model_key.lower() or model_key == config.GEMINI_MODEL_ID:
        from llm.gemini_adapter import GeminiAdapter
        adapter = GeminiAdapter()
    elif "groq" in model_key.lower() or "llama" in model_key.lower() or model_key == config.GROQ_MODEL_ID:
        from llm.groq_adapter import GroqAdapter
        adapter = GroqAdapter()
    else:
        raise ProviderError(f"No adapter registered for model_id: {model_key}")

    _MODEL_ADAPTER_CACHE[model_key] = adapter
    return adapter


# ---------------------------------------------------------------------------
# OmniRoute call
# ---------------------------------------------------------------------------

def _try_omniroute(
    model_id: str,
    messages: list[dict],
    tools: Optional[list[dict]],
    temperature: float,
    image_b64: Optional[str],
) -> LLMResponse:
    """
    Attempt to route the call through OmniRoute (OpenAI-compatible API).
    Raises ProviderError on any failure.
    """
    if not config.has_omniroute_credentials():
        raise ProviderError("OmniRoute credentials not configured")

    start = time.monotonic()
    payload: dict = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    # Multimodal: inject image into last user message if provided
    if image_b64:
        last_user_idx = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i].get("role") == "user"),
            None,
        )
        if last_user_idx is not None:
            payload["messages"] = list(messages)
            payload["messages"][last_user_idx] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": messages[last_user_idx].get("content", "")},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }

    headers = {
        "Authorization": f"Bearer {config.OMNIROUTE_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{config.OMNIROUTE_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
        elapsed_ms = (time.monotonic() - start) * 1000
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        result_text = choice.get("message", {}).get("content", "")
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)

        return LLMResponse(
            content=result_text,
            model_id=model_id,
            route_used="omniroute",
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=round(elapsed_ms, 2),
            cost_usd=_estimate_cost_generic(tokens_in, tokens_out),
        )
    except httpx.HTTPStatusError as e:
        raise ProviderError(f"OmniRoute HTTP {e.response.status_code}: {e.response.text[:200]}") from e
    except httpx.TimeoutException as e:
        raise ProviderError(f"OmniRoute timeout: {e}") from e
    except Exception as e:
        raise ProviderError(f"OmniRoute request failed: {e}") from e


def _estimate_cost_generic(tokens_in: int, tokens_out: int) -> float:
    """Generic cost estimate when routed through OmniRoute."""
    return round((tokens_in / 1000) * 0.001 + (tokens_out / 1000) * 0.002, 6)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chat_completion(
    model_id: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    temperature: float = 0.2,
    image_b64: Optional[str] = None,
) -> LLMResponse:
    """
    Route an LLM chat completion request.

    Priority:
      1. OmniRoute gateway (if credentials present)
      2. Direct provider adapter (always attempted as fallback)
      3. Deterministic FALLBACK response (if both fail — never crashes)

    All calls are logged to MemoryStore.
    """
    start_overall = time.monotonic()
    response: Optional[LLMResponse] = None
    errors: list[str] = []

    # --- Route 1: OmniRoute ---
    if config.has_omniroute_credentials():
        try:
            response = _try_omniroute(model_id, messages, tools, temperature, image_b64)
            logger.debug("OmniRoute success for model %s (%.0fms)", model_id, response.latency_ms)
        except Exception as e:
            errors.append(f"OmniRoute: {e}")
            logger.warning("OmniRoute failed for %s: %s — trying direct adapter", model_id, e)

    # --- Route 2: Direct adapter ---
    if response is None:
        try:
            adapter = _get_adapter(model_id)
            if image_b64 and hasattr(adapter, "complete"):
                import inspect
                sig = inspect.signature(adapter.complete)
                if "image_b64" in sig.parameters:
                    response = adapter.complete(messages, tools=tools, temperature=temperature, image_b64=image_b64)
                else:
                    response = adapter.complete(messages, tools=tools, temperature=temperature)
            else:
                response = adapter.complete(messages, tools=tools, temperature=temperature)
            logger.debug("Direct adapter success for model %s (%.0fms)", model_id, response.latency_ms)
        except ProviderError as e:
            errors.append(f"Direct adapter: {e}")
            logger.warning("Direct adapter failed for %s: %s — using deterministic fallback", model_id, e)
        except Exception as e:
            errors.append(f"Direct adapter unexpected: {e}")
            logger.error("Unexpected error in direct adapter for %s: %s", model_id, e)

    # --- Route 3: Deterministic fallback ---
    if response is None:
        elapsed_ms = (time.monotonic() - start_overall) * 1000
        error_summary = "; ".join(errors)
        response = LLMResponse(
            content=f"FALLBACK: LLM unavailable. Errors: {error_summary}",
            model_id=model_id,
            route_used="fallback",
            tokens_in=0,
            tokens_out=0,
            latency_ms=round(elapsed_ms, 2),
            cost_usd=0.0,
            is_fallback=True,
        )
        logger.error("All LLM routes failed for %s. Returning fallback response.", model_id)

    # --- Log to MemoryStore ---
    _log_to_store(response)

    return response


def _log_to_store(response: LLMResponse) -> None:
    """Log the LLM call to MemoryStore for observability."""
    try:
        from memory.store import store
        store.log_llm_call({
            "model_id": response.model_id,
            "route_used": response.route_used,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost_usd": response.cost_usd,
            "latency_ms": response.latency_ms,
            "is_fallback": response.is_fallback,
        })
    except Exception as e:
        logger.warning("Failed to log LLM call to MemoryStore: %s", e)


# ---------------------------------------------------------------------------
# CLI demo / self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=== LLM Gateway Self-Test ===")
    print(f"OmniRoute configured: {config.has_omniroute_credentials()}")
    print(f"IBM Granite configured: {config.has_ibm_credentials()}")
    print(f"Gemini configured: {config.has_gemini_credentials()}")
    print(f"Groq configured: {config.has_groq_credentials()}")
    print()

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Say hello in one sentence."},
    ]

    for model_key in [config.GRANITE_MODEL_ID, config.GEMINI_MODEL_ID, config.GROQ_MODEL_ID]:
        print(f"Testing model: {model_key}")
        resp = chat_completion(model_key, messages)
        print(f"  route_used : {resp.route_used}")
        print(f"  is_fallback: {resp.is_fallback}")
        print(f"  latency_ms : {resp.latency_ms}")
        print(f"  content    : {resp.content[:100]}")
        print()
