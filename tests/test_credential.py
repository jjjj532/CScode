"""Tests for P1-1: Credential System — event-sourced credential storage.

Tests cover:
- Credential model and types
- CredentialStore CRUD: create, get, list, update, delete
- Credential rotation
- Persistence across store instances
- Edge cases: non-existent, duplicates, empty values
"""

from __future__ import annotations

import pytest

from cscode.core.credential import Credential, CredentialStore
from cscode.storage.db import Database


# ─── Credential Model ────────────────────────────────────────────────


class TestCredentialModel:
    """Credential dataclass basic."""

    def test_create_api_key(self) -> None:
        cred = Credential(
            id="cred_001",
            name="OpenAI Key",
            type="api_key",
            value="sk-...",
            provider="openai",
        )
        assert cred.id == "cred_001"
        assert cred.name == "OpenAI Key"
        assert cred.type == "api_key"
        assert cred.value == "sk-..."
        assert cred.provider == "openai"
        assert cred.is_expired is False

    def test_credential_display_masks_secret(self) -> None:
        cred = Credential(
            id="cred_001", name="Key", type="api_key",
            value="sk-my-secret-key-12345", provider="openai",
        )
        display = cred.display_value
        # Should show prefix + mask
        assert display.startswith("sk-")
        assert "***" in display
        # Should not contain full secret
        assert "12345" not in display

    def test_credential_short_value_not_masked(self) -> None:
        cred = Credential(
            id="cred_001", name="Short", type="custom",
            value="ab", provider="custom",
        )
        assert cred.display_value == "ab"

    def test_is_expired_with_expiry(self) -> None:
        import time
        cred = Credential(
            id="cred_001", name="Token", type="oauth_token",
            value="tok_xxx", provider="custom",
            expires_at=time.time() - 100,  # expired 100s ago
        )
        assert cred.is_expired is True

    def test_not_expired(self) -> None:
        import time
        cred = Credential(
            id="cred_001", name="Token", type="oauth_token",
            value="tok_xxx", provider="custom",
            expires_at=time.time() + 3600,  # expires in 1h
        )
        assert cred.is_expired is False

    def test_no_expiry(self) -> None:
        cred = Credential(
            id="cred_001", name="Key", type="api_key",
            value="sk-xxx", provider="openai",
        )
        assert cred.is_expired is False


# ─── CredentialStore CRUD ────────────────────────────────────────────


@pytest.fixture
async def store() -> CredentialStore:
    db = Database(":memory:")
    await db.init()
    return CredentialStore(db)


class TestCredentialStoreCreate:
    @pytest.mark.asyncio
    async def test_create(self, store: CredentialStore) -> None:
        cred = await store.create(
            name="OpenAI Key",
            type="api_key",
            value="sk-test-key",
            provider="openai",
        )
        assert cred.id is not None
        assert cred.id.startswith("cred_")
        assert cred.name == "OpenAI Key"
        assert cred.type == "api_key"
        assert cred.value == "sk-test-key"
        assert cred.provider == "openai"
        assert cred.created_at > 0

    @pytest.mark.asyncio
    async def test_create_empty_name_raises(self, store: CredentialStore) -> None:
        with pytest.raises(ValueError, match="name"):
            await store.create(name="", type="api_key", value="v", provider="p")

    @pytest.mark.asyncio
    async def test_create_empty_value_raises(self, store: CredentialStore) -> None:
        with pytest.raises(ValueError, match="value"):
            await store.create(name="Key", type="api_key", value="", provider="p")

    @pytest.mark.asyncio
    async def test_create_invalid_type_raises(self, store: CredentialStore) -> None:
        with pytest.raises(ValueError, match="type"):
            await store.create(name="K", type="invalid_type", value="v", provider="p")


class TestCredentialStoreGet:
    @pytest.mark.asyncio
    async def test_get(self, store: CredentialStore) -> None:
        created = await store.create(name="Key", type="api_key", value="sk-val", provider="openai")
        fetched = await store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.value == "sk-val"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, store: CredentialStore) -> None:
        fetched = await store.get("cred_nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_get_empty_id(self, store: CredentialStore) -> None:
        fetched = await store.get("")
        assert fetched is None


class TestCredentialStoreList:
    @pytest.mark.asyncio
    async def test_list_empty(self, store: CredentialStore) -> None:
        assert await store.list() == []

    @pytest.mark.asyncio
    async def test_list(self, store: CredentialStore) -> None:
        await store.create(name="Key1", type="api_key", value="v1", provider="openai")
        await store.create(name="Key2", type="api_key", value="v2", provider="anthropic")
        all_creds = await store.list()
        assert len(all_creds) == 2

    @pytest.mark.asyncio
    async def test_list_by_provider(self, store: CredentialStore) -> None:
        await store.create(name="K1", type="api_key", value="v1", provider="openai")
        await store.create(name="K2", type="api_key", value="v2", provider="anthropic")
        openai_creds = await store.list(provider="openai")
        assert len(openai_creds) == 1
        assert openai_creds[0].provider == "openai"

    @pytest.mark.asyncio
    async def test_list_by_type(self, store: CredentialStore) -> None:
        await store.create(name="K1", type="api_key", value="v1", provider="openai")
        await store.create(name="T1", type="oauth_token", value="v2", provider="custom")
        keys = await store.list(cred_type="api_key")
        assert len(keys) == 1
        assert keys[0].type == "api_key"


class TestCredentialStoreUpdate:
    @pytest.mark.asyncio
    async def test_update_name(self, store: CredentialStore) -> None:
        created = await store.create(name="Old", type="api_key", value="v", provider="openai")
        updated = await store.update(created.id, name="New Name")
        assert updated is not None
        assert updated.name == "New Name"
        assert updated.value == "v"  # unchanged

    @pytest.mark.asyncio
    async def test_update_value(self, store: CredentialStore) -> None:
        created = await store.create(name="Key", type="api_key", value="old-val", provider="openai")
        updated = await store.update(created.id, value="new-val")
        assert updated is not None
        assert updated.value == "new-val"

    @pytest.mark.asyncio
    async def test_update_nonexistent(self, store: CredentialStore) -> None:
        result = await store.update("cred_nonexistent", name="X")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_no_changes(self, store: CredentialStore) -> None:
        created = await store.create(name="Key", type="api_key", value="v", provider="openai")
        updated = await store.update(created.id)
        assert updated is not None
        assert updated.name == "Key"


class TestCredentialStoreDelete:
    @pytest.mark.asyncio
    async def test_delete(self, store: CredentialStore) -> None:
        created = await store.create(name="Key", type="api_key", value="v", provider="openai")
        result = await store.delete(created.id)
        assert result is True
        assert await store.get(created.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, store: CredentialStore) -> None:
        result = await store.delete("cred_nonexistent")
        assert result is False


class TestCredentialStoreRotate:
    @pytest.mark.asyncio
    async def test_rotate(self, store: CredentialStore) -> None:
        created = await store.create(name="Key", type="api_key", value="old-value", provider="openai")
        rotated = await store.rotate(created.id, "new-value")
        assert rotated is not None
        assert rotated.value == "new-value"
        assert rotated.rotated_at is not None
        assert rotated.previous_value == "old-value"

    @pytest.mark.asyncio
    async def test_rotate_same_value_raises(self, store: CredentialStore) -> None:
        created = await store.create(name="Key", type="api_key", value="same", provider="openai")
        with pytest.raises(ValueError, match="must differ"):
            await store.rotate(created.id, "same")

    @pytest.mark.asyncio
    async def test_rotate_nonexistent(self, store: CredentialStore) -> None:
        result = await store.rotate("cred_nonexistent", "new")
        assert result is None


class TestCredentialStorePersistence:
    @pytest.mark.asyncio
    async def test_persistence(self) -> None:
        db = Database(":memory:")
        await db.init()
        store1 = CredentialStore(db)
        created = await store1.create(name="Key", type="api_key", value="persistent-value", provider="openai")

        store2 = CredentialStore(db)
        fetched = await store2.get(created.id)
        assert fetched is not None
        assert fetched.value == "persistent-value"

    @pytest.mark.asyncio
    async def test_rotation_history_preserved(self) -> None:
        db = Database(":memory:")
        await db.init()
        store = CredentialStore(db)
        c = await store.create(name="K", type="api_key", value="v1", provider="openai")
        await store.rotate(c.id, "v2")
        await store.rotate(c.id, "v3")

        store2 = CredentialStore(db)
        fetched = await store2.get(c.id)
        assert fetched is not None
        assert fetched.value == "v3"
        assert fetched.previous_value == "v2"
