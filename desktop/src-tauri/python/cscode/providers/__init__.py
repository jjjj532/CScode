from __future__ import annotations

from cscode.core.config import Config
from cscode.providers.base import LLMProvider


def create_provider(config: Config) -> LLMProvider:
    provider = config.provider.lower() if config.provider else "openai"

    match provider:
        case "openai":
            from cscode.providers.openai import OpenAIProvider
            return OpenAIProvider(config)
        case "anthropic":
            from cscode.providers.anthropic import AnthropicProvider
            return AnthropicProvider(config)
        case "ollama":
            from cscode.providers.ollama import OllamaProvider
            return OllamaProvider(config)
        case _:
            from cscode.providers.openai import OpenAIProvider
            return OpenAIProvider(config)
