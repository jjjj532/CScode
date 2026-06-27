"""LLM adapter implementations.

Adapters wrap existing provider implementations to conform
to the LLMService interface defined in llm/service.py.
"""

from cscode.llm.adapters.legacy import LegacyProviderAdapter

__all__ = [
    "LegacyProviderAdapter",
]
