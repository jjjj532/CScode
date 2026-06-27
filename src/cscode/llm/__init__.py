"""CScode LLM Layer — typed LLM generation with automatic tool loop.

Dependency direction: schema ← llm (LLM depends on schema, nothing else).

This module provides:
  - LLMService:    Abstract interface for generation with tool loop
  - LLMResponse:   Typed result of a generation cycle
  - ToolExecution: Record of one tool call within the cycle
  - LegacyProviderAdapter: Bridge from old provider system to LLMService
"""

from cscode.llm.adapters import LegacyProviderAdapter
from cscode.llm.service import LLMResponse, LLMService, ToolExecution

__all__ = [
    "LLMService",
    "LLMResponse",
    "ToolExecution",
    "LegacyProviderAdapter",
]
