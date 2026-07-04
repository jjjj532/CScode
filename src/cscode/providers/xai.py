from __future__ import annotations

from cscode.core.config import Config
from cscode.providers.openai import OpenAIProvider
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class XAIProvider(OpenAIProvider):
    """xAI provider using OpenAI-compatible chat completions endpoint.

    API docs: https://docs.x.ai/api
    Base URL: https://api.x.ai/v1
    """

    def __init__(self, config: Config) -> None:
        config.api_base = config.api_base or "https://api.x.ai/v1"
        if config.model == "gpt-4o":
            config.model = "grok-2-latest"
        super().__init__(config)
        logger.info("XAIProvider initialized: model=%s", self._model)
