"""Catalog system — model/provider/agent registry.

Provides structured directories for discovering available models,
providers, and agents across the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelEntry:
    """A model available through a provider."""

    id: str
    name: str
    provider: str
    capabilities: list[str] = field(default_factory=list)
    context_length: int | None = None
    pricing: dict[str, float] | None = None


@dataclass
class ProviderEntry:
    """An LLM provider."""

    id: str
    name: str
    models: list[str] = field(default_factory=list)
    api_type: str = "openai"


@dataclass
class AgentEntry:
    """A built-in or registered agent."""

    id: str
    name: str
    description: str = ""
    tools: list[str] = field(default_factory=list)


class Catalog:
    """Directory of models, providers, and agents.

    Provides registration, lookup, listing, and search operations
    for all three entity types.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelEntry] = {}
        self._providers: dict[str, ProviderEntry] = {}
        self._agents: dict[str, AgentEntry] = {}

    # ── Models ──────────────────────────────────────────────────────

    def register_model(self, entry: ModelEntry) -> None:
        """Register a model entry. Overwrites if id already exists."""
        if not entry.id:
            raise ValueError("Model id is required")
        self._models[entry.id] = entry

    def get_model(self, model_id: str) -> ModelEntry | None:
        """Look up a model by id."""
        return self._models.get(model_id)

    def list_models(self, provider: str | None = None) -> list[ModelEntry]:
        """List all models, optionally filtered by provider.

        Returns models in registration order (insertion-ordered dict).
        """
        if provider is None:
            return list(self._models.values())
        return [m for m in self._models.values() if m.provider == provider]

    def search_models(self, query: str) -> list[ModelEntry]:
        """Search models by id, name, provider, or capabilities.

        Performs a case-insensitive substring match. Returns all
        models when the query is empty.
        """
        if not query:
            return list(self._models.values())
        q = query.lower()
        results: list[ModelEntry] = []
        for m in self._models.values():
            if (
                q in m.id.lower()
                or q in m.name.lower()
                or q in m.provider.lower()
                or any(q in c.lower() for c in m.capabilities)
            ):
                results.append(m)
        return results

    def get_default_model(self, provider_id: str) -> str | None:
        """Return the first registered model id for the given provider."""
        for m in self._models.values():
            if m.provider == provider_id:
                return m.id
        return None

    def get_default_models(self) -> dict[str, str]:
        """Return a mapping of provider_id -> default model id."""
        defaults: dict[str, str] = {}
        for m in self._models.values():
            if m.provider not in defaults:
                defaults[m.provider] = m.id
        return defaults

    # ── Providers ───────────────────────────────────────────────────

    def register_provider(self, entry: ProviderEntry) -> None:
        """Register a provider entry."""
        if not entry.id:
            raise ValueError("Provider id is required")
        self._providers[entry.id] = entry

    def get_provider(self, provider_id: str) -> ProviderEntry | None:
        """Look up a provider by id."""
        return self._providers.get(provider_id)

    def list_providers(self) -> list[ProviderEntry]:
        """List all registered providers."""
        return list(self._providers.values())

    # ── Agents ──────────────────────────────────────────────────────

    def register_agent(self, entry: AgentEntry) -> None:
        """Register an agent entry."""
        if not entry.id:
            raise ValueError("Agent id is required")
        self._agents[entry.id] = entry

    def get_agent(self, agent_id: str) -> AgentEntry | None:
        """Look up an agent by id."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentEntry]:
        """List all registered agents."""
        return list(self._agents.values())
