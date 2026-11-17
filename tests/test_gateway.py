"""
tests/test_gateway.py — Tests for the LLM Gateway fallback logic.

Uses mocked adapters to verify routing decisions without real API calls.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest

from llm.gateway import LLMResponse, ProviderError, chat_completion, _MODEL_ADAPTER_CACHE


def _make_success_response(route: str = "mock_direct") -> LLMResponse:
    return LLMResponse(
        content="Hello from mock LLM.",
        model_id="test-model",
        route_used=route,
        tokens_in=10,
        tokens_out=5,
        latency_ms=42.0,
        cost_usd=0.000015,
        is_fallback=False,
    )


class TestGatewayFallbackLogic:
    def setup_method(self):
        # Clear adapter cache between tests
        _MODEL_ADAPTER_CACHE.clear()

    def _make_adapter_mock(self, response: LLMResponse):
        mock = MagicMock()
        mock.complete.return_value = response
        return mock

    def _make_adapter_mock_failing(self, error_msg: str = "API error"):
        mock = MagicMock()
        mock.complete.side_effect = ProviderError(error_msg)
        return mock

    def test_fallback_response_when_no_credentials(self):
        """When no credentials exist, should return a fallback response (never raise)."""
        with patch("config.has_omniroute_credentials", return_value=False), \
             patch("config.has_ibm_credentials", return_value=False), \
             patch("config.has_gemini_credentials", return_value=False), \
             patch("config.has_groq_credentials", return_value=False), \
             patch("config.GRANITE_MODEL_ID", "ibm/granite-3-8b-instruct"), \
             patch("config.GEMINI_MODEL_ID", "gemini-2.0-flash"), \
             patch("config.GROQ_MODEL_ID", "llama-3.3-70b-versatile"), \
             patch("config.GEMINI_API_KEY", ""):  # No OpenRouter key either

            resp = chat_completion("ibm/granite-3-8b-instruct", [{"role": "user", "content": "hi"}])
            assert resp.is_fallback is True
            assert "FALLBACK" in resp.content
            assert resp.route_used == "fallback"

    def test_omniroute_success_used_first(self):
        """When OmniRoute succeeds, it should be the route used."""
        omniroute_response = _make_success_response("omniroute")

        with patch("config.has_omniroute_credentials", return_value=True), \
             patch("llm.gateway._try_omniroute", return_value=omniroute_response):
            resp = chat_completion("ibm/granite-3-8b-instruct", [{"role": "user", "content": "hi"}])
            assert resp.route_used == "omniroute"
            assert resp.is_fallback is False

    def test_omniroute_failure_falls_back_to_direct(self):
        """When OmniRoute fails, the direct adapter should be tried."""
        direct_response = _make_success_response("ibm_granite_direct")
        mock_adapter = self._make_adapter_mock(direct_response)

        with patch("config.has_omniroute_credentials", return_value=True), \
             patch("llm.gateway._try_omniroute", side_effect=ProviderError("OmniRoute down")), \
             patch("llm.gateway._get_adapter", return_value=mock_adapter):
            resp = chat_completion("ibm/granite-3-8b-instruct", [{"role": "user", "content": "hi"}])
            assert resp.route_used == "ibm_granite_direct"
            assert resp.is_fallback is False
            mock_adapter.complete.assert_called_once()

    def test_both_routes_fail_returns_fallback(self):
        """When both OmniRoute and direct adapter fail, a deterministic fallback is returned."""
        mock_adapter = self._make_adapter_mock_failing("Direct adapter offline")

        with patch("config.has_omniroute_credentials", return_value=True), \
             patch("llm.gateway._try_omniroute", side_effect=ProviderError("OmniRoute down")), \
             patch("llm.gateway._get_adapter", return_value=mock_adapter):
            resp = chat_completion("ibm/granite-3-8b-instruct", [{"role": "user", "content": "hi"}])
            assert resp.is_fallback is True
            assert resp.route_used == "fallback"
            assert "FALLBACK" in resp.content

    def test_fallback_response_contains_error_info(self):
        """Fallback content should include the error messages."""
        mock_adapter = self._make_adapter_mock_failing("Connection refused")

        with patch("config.has_omniroute_credentials", return_value=True), \
             patch("llm.gateway._try_omniroute", side_effect=ProviderError("Timeout")), \
             patch("llm.gateway._get_adapter", return_value=mock_adapter):
            resp = chat_completion("test-model", [{"role": "user", "content": "hi"}])
            assert "Timeout" in resp.content or "Connection refused" in resp.content

    def test_no_omniroute_goes_directly_to_adapter(self):
        """When OmniRoute is not configured, skip it entirely and use direct adapter."""
        direct_response = _make_success_response("groq_direct")
        mock_adapter = self._make_adapter_mock(direct_response)

        with patch("config.has_omniroute_credentials", return_value=False), \
             patch("llm.gateway._get_adapter", return_value=mock_adapter):
            resp = chat_completion("llama-3.3-70b-versatile", [{"role": "user", "content": "hi"}])
            assert resp.route_used == "groq_direct"
            assert resp.is_fallback is False

    def test_llm_call_logged_to_memory_store(self):
        """Every call should be logged to MemoryStore."""
        from memory.store import store
        store.reset()

        direct_response = _make_success_response("mock_direct")
        mock_adapter = self._make_adapter_mock(direct_response)

        with patch("config.has_omniroute_credentials", return_value=False), \
             patch("llm.gateway._get_adapter", return_value=mock_adapter):
            chat_completion("test-model", [{"role": "user", "content": "hi"}])

        log = store.get_llm_call_log(last_n=1)
        assert len(log) == 1
        assert log[0]["model_id"] == "test-model"
        assert log[0]["route_used"] == "mock_direct"

    def test_fallback_response_logged_to_memory_store(self):
        """Even fallback responses should be logged."""
        from memory.store import store
        store.reset()

        mock_adapter = self._make_adapter_mock_failing("offline")

        with patch("config.has_omniroute_credentials", return_value=False), \
             patch("llm.gateway._get_adapter", return_value=mock_adapter):
            chat_completion("test-model", [{"role": "user", "content": "hi"}])

        log = store.get_llm_call_log(last_n=1)
        assert len(log) == 1
        assert log[0]["is_fallback"] is True

    def test_response_is_llmresponse_instance(self):
        """chat_completion always returns an LLMResponse, never raises."""
        with patch("config.has_omniroute_credentials", return_value=False), \
             patch("config.has_ibm_credentials", return_value=False), \
             patch("config.has_gemini_credentials", return_value=False), \
             patch("config.has_groq_credentials", return_value=False), \
             patch("config.GRANITE_MODEL_ID", "ibm/granite-3-8b-instruct"):
            resp = chat_completion("ibm/granite-3-8b-instruct", [{"role": "user", "content": "hi"}])
            assert isinstance(resp, LLMResponse)

    def test_tokens_non_negative(self):
        """Fallback response should have non-negative token counts."""
        with patch("config.has_omniroute_credentials", return_value=False), \
             patch("config.has_ibm_credentials", return_value=False), \
             patch("config.has_gemini_credentials", return_value=False), \
             patch("config.has_groq_credentials", return_value=False), \
             patch("config.GRANITE_MODEL_ID", "ibm/granite-3-8b-instruct"):
            resp = chat_completion("ibm/granite-3-8b-instruct", [{"role": "user", "content": "hi"}])
            assert resp.tokens_in >= 0
            assert resp.tokens_out >= 0
            assert resp.cost_usd >= 0.0
