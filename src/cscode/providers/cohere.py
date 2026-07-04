from __future__ import annotations

from cscode.core.config import Config
from cscode.providers.openai import OpenAIProvider
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class CohereProvider(OpenAIProvider):
    """Cohere provider using OpenAI-compatible chat completions endpoint.

    API docs: https://docs.cohere.com/reference/chat
    Base URL: https://api.cohere.com/v1
    """

    def __init__(self, config: Config) -> None:
        config.api_base = config.api_base or "https://api.cohere.com/v1"
        if config.model == "gpt-4o":
            config.model = "command-r-plus"
        super().__init__(config)
        logger.info("CohereProvider initialized: model=%s", self._model)
