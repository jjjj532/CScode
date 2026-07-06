from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from cscode.core.config import Config
from cscode.core.errors import ProviderError
from cscode.core.messages import Message, MessageRole
from cscode.providers.base import LLMProvider, LLMResult
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


class BedrockProvider(LLMProvider):
    """Amazon Bedrock provider via Converse API.

    Requires ``boto3`` and AWS credentials configured via environment
    (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION) or ~/.aws/config.

    API docs: https://docs.aws.amazon.com/bedrock/latest/APIReference
    """

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        if config.model and config.model != "gpt-4o":
            self._model = config.model
        else:
            self._model = "anthropic.claude-3-5-sonnet-20241022"
        self._region = config.api_base or "us-east-1"
        logger.info(
            "BedrockProvider initialized: model=%s region=%s",
            self._model,
            self._region,
        )

    @property
    def model(self) -> str:
        return self._model

    async def _ensure_client(self) -> Any:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError:
            raise ProviderError(
                "Bedrock provider requires boto3: pip install boto3"
            ) from None
        session = boto3.Session(region_name=self._region)
        return session.client("bedrock-runtime")

    def build_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                continue
            role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
            content: list[dict[str, str]] = [{"text": msg.content or ""}]
            result.append({"role": role, "content": content})
        return result

    def _extract_system(self, messages: list[Message]) -> list[dict[str, str]]:
        systems = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM and msg.content:
                systems.append({"text": msg.content})
        return systems

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResult:
        logger.info("Bedrock.complete: model=%s messages=%d", self._model, len(messages))
        client = await self._ensure_client()
        body: dict[str, Any] = {
            "modelId": self._model,
            "messages": self.build_messages(messages),
        }
        system = self._extract_system(messages)
        if system:
            body["system"] = system
        if tools:
            body["toolConfig"] = {"tools": tools}
        body["inferenceConfig"] = {
            "maxTokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "topP": self.config.top_p,
        }

        try:
            response = client.converse(**body)
        except Exception as e:
            logger.error("Bedrock API error: %s", e)
            raise ProviderError(f"Bedrock API error: {e}") from e

        output = response.get("output", {})
        message = output.get("message", {})
        content_blocks = message.get("content", [])
        text = ""
        for block in content_blocks:
            if "text" in block:
                text += block["text"]

        usage = response.get("usage", {})
        stop_reason = response.get("stopReason", "")
        return LLMResult(
            content=text,
            usage=usage,
            model=self._model,
            finish_reason=stop_reason,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        logger.info("Bedrock.stream: model=%s messages=%d", self._model, len(messages))
        client = await self._ensure_client()
        body: dict[str, Any] = {
            "modelId": self._model,
            "messages": self.build_messages(messages),
        }
        system = self._extract_system(messages)
        if system:
            body["system"] = system
        if tools:
            body["toolConfig"] = {"tools": tools}
        body["inferenceConfig"] = {
            "maxTokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "topP": self.config.top_p,
        }

        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _producer() -> None:
            """Synchronous boto3 stream producer running in a thread."""
            try:
                response = client.converse_stream(**body)
                event_stream = response.get("stream", [])
                for event in event_stream:
                    if "contentBlockDelta" in event:
                        delta = event["contentBlockDelta"]
                        text = delta.get("delta", {}).get("text", "")
                        if text:
                            queue.put_nowait(text)
                queue.put_nowait(None)  # sentinel
            except Exception as e:
                logger.error("Bedrock stream error: %s", e)
                queue.put_nowait(None)

        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, _producer)

        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
            await task
        except Exception as e:
            logger.error("Bedrock stream failed: %s", e)
            raise ProviderError(f"Bedrock stream error: {e}") from e
