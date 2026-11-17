# llm/__init__.py
from llm.gateway import chat_completion, LLMResponse, ProviderError

__all__ = ["chat_completion", "LLMResponse", "ProviderError"]
