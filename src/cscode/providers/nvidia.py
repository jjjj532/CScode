from __future__ import annotations

from cscode.core.config import Config
from cscode.providers.openai import OpenAIProvider
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class NvidiaProvider(OpenAIProvider):
    """Nvidia NIM provider using OpenAI-compatible chat completions endpoint.

    API docs: https://build.nvidia.com/docs
    Base URL: https://integrate.api.nvidia.com/v1
    """

    def __init__(self, config: Config) -> None:
        config.api_base = config.api_base or "https://integrate.api.nvidia.com/v1"
        if config.model == "gpt-4o":
            config.model = "meta/llama-3.1-70b-instruct"
        super().__init__(config)
        logger.info("NvidiaProvider initialized: model=%s", self._model)
