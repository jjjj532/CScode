from __future__ import annotations

from cscode.core.config import Config
from cscode.core.errors import ProviderError
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
        case "gemini":
            from cscode.providers.gemini import GeminiProvider
            return GeminiProvider(config)
        case "azure":
            from cscode.providers.azure import AzureProvider
            return AzureProvider(config)
        case "openrouter":
            from cscode.providers.openrouter import OpenRouterProvider
            return OpenRouterProvider(config)
        case "cohere":
            from cscode.providers.cohere import CohereProvider
            return CohereProvider(config)
        case "grok":
            from cscode.providers.grok import GrokProvider
            return GrokProvider(config)
        case "mistral":
            from cscode.providers.mistral import MistralProvider
            return MistralProvider(config)
        case "nvidia":
            from cscode.providers.nvidia import NvidiaProvider
            return NvidiaProvider(config)
        case "perplexity":
            from cscode.providers.perplexity import PerplexityProvider
            return PerplexityProvider(config)
        case "xai":
            from cscode.providers.xai import XAIProvider
            return XAIProvider(config)
        case "bedrock":
            from cscode.providers.bedrock import BedrockProvider
            return BedrockProvider(config)
        case "vertex":
            from cscode.providers.vertex import VertexProvider
            return VertexProvider(config)
        case "custom" | "scnet":
            from cscode.providers.openai import OpenAIProvider
            return OpenAIProvider(config)
        case _:
            msg = f"Unknown provider: {provider}"
            raise ProviderError(msg)
