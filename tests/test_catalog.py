"""Tests for P1-4: Catalog 系统 — model/provider/agent registry.

Tests cover:
- ModelEntry, ProviderEntry, AgentEntry data models
- Catalog register/get/list/search operations
- Default model resolution
- Edge cases: duplicates, missing entries, empty catalog
"""

from __future__ import annotations

from dataclasses import asdict

import pytest

from cscode.core.catalog import (
    AgentEntry,
    Catalog,
    ModelEntry,
    ProviderEntry,
)

# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def gpt4() -> ModelEntry:
    return ModelEntry(
        id="gpt-4o",
        name="GPT-4o",
        provider="openai",
        capabilities=["chat", "tools", "vision"],
        context_length=128000,
    )


@pytest.fixture
def claude() -> ModelEntry:
    return ModelEntry(
        id="claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        provider="anthropic",
        capabilities=["chat", "tools", "vision", "thinking"],
        context_length=200000,
    )


@pytest.fixture
def llama() -> ModelEntry:
    return ModelEntry(
        id="llama-3.1-70b",
        name="Llama 3.1 70B",
        provider="ollama",
        capabilities=["chat", "tools"],
        context_length=32768,
    )


@pytest.fixture
def openai_provider() -> ProviderEntry:
    return ProviderEntry(
        id="openai",
        name="OpenAI",
        models=["gpt-4o", "gpt-4o-mini"],
        api_type="openai",
    )


@pytest.fixture
def catalog(gpt4: ModelEntry, claude: ModelEntry, llama: ModelEntry, openai_provider: ProviderEntry) -> Catalog:
    c = Catalog()
    c.register_model(gpt4)
    c.register_model(claude)
    c.register_model(llama)
    c.register_provider(openai_provider)
    c.register_agent(AgentEntry(
        id="code-reviewer",
        name="Code Reviewer",
        description="Reviews code for quality and security",
        tools=["read", "grep", "glob"],
    ))
    return c


# ─── Data Models ────────────────────────────────────────────────────


class TestModelEntry:
    def test_create(self) -> None:
        m = ModelEntry(id="test", name="Test Model", provider="test", capabilities=["chat"])
        assert m.id == "test"
        assert m.name == "Test Model"

    def test_default_pricing_is_none(self) -> None:
        m = ModelEntry(id="t", name="T", provider="p", capabilities=[])
        assert m.pricing is None

    def test_default_context_length_is_none(self) -> None:
        m = ModelEntry(id="t", name="T", provider="p", capabilities=[])
        assert m.context_length is None


class TestProviderEntry:
    def test_create(self) -> None:
        p = ProviderEntry(id="p", name="P", models=["m1"], api_type="openai")
        assert p.id == "p"
        assert p.api_type == "openai"


class TestAgentEntry:
    def test_create(self) -> None:
        a = AgentEntry(id="a", name="A", description="desc", tools=["read"])
        assert a.id == "a"
        assert "read" in a.tools


# ─── Model Operations ───────────────────────────────────────────────


class TestCatalogModels:
    def test_register_and_get(self, catalog: Catalog, gpt4: ModelEntry) -> None:
        assert catalog.get_model("gpt-4o") == gpt4

    def test_get_nonexistent_returns_none(self, catalog: Catalog) -> None:
        assert catalog.get_model("nonexistent") is None

    def test_register_duplicate_overwrites(self, catalog: Catalog) -> None:
        updated = ModelEntry(id="gpt-4o", name="GPT-4o Updated", provider="openai", capabilities=[])
        catalog.register_model(updated)
        assert catalog.get_model("gpt-4o") == updated

    def test_list_all_models(self, catalog: Catalog) -> None:
        models = catalog.list_models()
        assert len(models) == 3

    def test_list_models_by_provider(self, catalog: Catalog) -> None:
        models = catalog.list_models(provider="openai")
        assert len(models) == 1
        assert models[0].id == "gpt-4o"

    def test_list_models_by_provider_no_match(self, catalog: Catalog) -> None:
        models = catalog.list_models(provider="nonexistent")
        assert models == []

    def test_search_models_by_name(self, catalog: Catalog) -> None:
        results = catalog.search_models("claude")
        assert len(results) == 1
        assert results[0].id == "claude-sonnet-4-5"

    def test_search_models_by_capability(self, catalog: Catalog) -> None:
        results = catalog.search_models("vision")
        assert len(results) == 2
        ids = {m.id for m in results}
        assert "gpt-4o" in ids
        assert "claude-sonnet-4-5" in ids

    def test_search_models_no_match(self, catalog: Catalog) -> None:
        results = catalog.search_models("quantum")
        assert results == []

    def test_search_models_case_insensitive(self, catalog: Catalog) -> None:
        results = catalog.search_models("CLAUDE")
        assert len(results) == 1

    def test_get_default_model_for_provider(self, catalog: Catalog) -> None:
        default = catalog.get_default_model("openai")
        assert default == "gpt-4o"

    def test_get_default_model_unknown_provider(self, catalog: Catalog) -> None:
        default = catalog.get_default_model("nonexistent")
        assert default is None

    def test_get_default_models_returns_dict(self, catalog: Catalog) -> None:
        defaults = catalog.get_default_models()
        assert defaults["openai"] == "gpt-4o"
        assert defaults["anthropic"] == "claude-sonnet-4-5"
        assert defaults["ollama"] == "llama-3.1-70b"


# ─── Provider Operations ────────────────────────────────────────────


class TestCatalogProviders:
    def test_register_and_get_provider(self, catalog: Catalog, openai_provider: ProviderEntry) -> None:
        assert catalog.get_provider("openai") == openai_provider

    def test_get_nonexistent_provider(self, catalog: Catalog) -> None:
        assert catalog.get_provider("nonexistent") is None

    def test_list_providers(self, catalog: Catalog) -> None:
        providers = catalog.list_providers()
        assert len(providers) == 1
        assert providers[0].id == "openai"


# ─── Agent Operations ────────────────────────────────────────────────


class TestCatalogAgents:
    def test_register_and_get_agent(self, catalog: Catalog) -> None:
        agent = catalog.get_agent("code-reviewer")
        assert agent is not None
        assert agent.name == "Code Reviewer"

    def test_get_nonexistent_agent(self, catalog: Catalog) -> None:
        assert catalog.get_agent("nonexistent") is None

    def test_list_agents(self, catalog: Catalog) -> None:
        agents = catalog.list_agents()
        assert len(agents) == 1


# ─── Empty Catalog ─────────────────────────────────────────────────


class TestEmptyCatalog:
    @pytest.fixture
    def empty(self) -> Catalog:
        return Catalog()

    def test_list_models_empty(self, empty: Catalog) -> None:
        assert empty.list_models() == []

    def test_list_providers_empty(self, empty: Catalog) -> None:
        assert empty.list_providers() == []

    def test_list_agents_empty(self, empty: Catalog) -> None:
        assert empty.list_agents() == []

    def test_get_default_models_empty(self, empty: Catalog) -> None:
        assert empty.get_default_models() == {}


# ─── Edge Cases ─────────────────────────────────────────────────────


class TestCatalogEdgeCases:
    def test_register_model_without_id(self) -> None:
        with pytest.raises(ValueError, match="id"):
            Catalog().register_model(ModelEntry(id="", name="Bad", provider="p", capabilities=[]))

    def test_register_provider_without_id(self) -> None:
        with pytest.raises(ValueError):
            Catalog().register_provider(ProviderEntry(id="", name="Bad", models=[], api_type="openai"))

    def test_search_empty_string(self, catalog: Catalog) -> None:
        results = catalog.search_models("")
        # Empty query returns all models
        assert len(results) == 3

    def test_model_asdict(self, gpt4: ModelEntry) -> None:
        d = asdict(gpt4)
        assert d["id"] == "gpt-4o"
        assert d["provider"] == "openai"
