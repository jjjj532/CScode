from __future__ import annotations

from cscode.core.config import Config
from cscode.providers.openai import OpenAIProvider
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class PerplexityProvider(OpenAIProvider):
    """Perplexity AI provider using OpenAI-compatible chat completions endpoint.

    API docs: https://docs.perplexity.ai/api-reference/chat-completions
    Base URL: https://api.perplexity.ai
    """

    def __init__(self, config: Config) -> None:
        config.api_base = config.api_base or "https://api.perplexity.ai"
        if config.model == "gpt-4o":
            config.model = "sonar-pro"
        super().__init__(config)
        logger.info("PerplexityProvider initialized: model=%s", self._model)
