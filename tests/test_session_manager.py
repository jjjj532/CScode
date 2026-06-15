import pytest
from unittest.mock import AsyncMock, MagicMock
from cscode.core.session_manager import SessionManager, Session, SessionStatus
from cscode.storage.session import SessionStore


@pytest.mark.asyncio
async def test_create_session():
    manager = SessionManager()
    session = await manager.create(title="Test Session")

    assert session.id is not None
    assert session.title == "Test Session"
    assert session.status == SessionStatus.ACTIVE


@pytest.mark.asyncio
async def test_list_sessions():
    manager = SessionManager()
    s1 = await manager.create(title="Session 1")
    s2 = await manager.create(title="Session 2")

    sessions = manager.list()
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_set_active_session():
    manager = SessionManager()
    s1 = await manager.create(title="Session 1")
    s2 = await manager.create(title="Session 2")

    manager.set_active(s2.id)
    assert manager.get_active().id == s2.id


@pytest.mark.asyncio
async def test_remove_session():
    manager = SessionManager()
    s1 = await manager.create(title="Session 1")

    result = await manager.remove(s1.id)
    assert result is True
    assert manager.get(s1.id) is None


@pytest.mark.asyncio
async def test_max_sessions_limit():
    manager = SessionManager(max_sessions=2)
    await manager.create(title="Session 1")
    await manager.create(title="Session 2")

    with pytest.raises(ValueError, match="Maximum sessions"):
        await manager.create(title="Session 3")


def test_get_invalid_session_id():
    manager = SessionManager()

    result = manager.get("invalid-id")
    assert result is None


@pytest.mark.asyncio
async def test_remove_invalid_session_id():
    manager = SessionManager()
    await manager.create(title="Session 1")

    result = await manager.remove("invalid-id")
    assert result is False


@pytest.mark.asyncio
async def test_set_active_invalid_session_id():
    manager = SessionManager()
    await manager.create(title="Session 1")

    result = manager.set_active("invalid-id")
    assert result is False


@pytest.mark.asyncio
async def test_remove_active_session_last_remaining():
    manager = SessionManager()
    s1 = await manager.create(title="Session 1")

    await manager.remove(s1.id)
    assert manager.get_active() is None


def test_max_sessions_zero_raises_error():
    with pytest.raises(ValueError, match="max_sessions"):
        SessionManager(max_sessions=0)


@pytest.mark.asyncio
async def test_create_empty_provider_raises_error():
    manager = SessionManager()

    with pytest.raises(ValueError, match="provider"):
        await manager.create(provider="")


@pytest.mark.asyncio
async def test_create_empty_model_raises_error():
    manager = SessionManager()

    with pytest.raises(ValueError, match="model"):
        await manager.create(model="")


@pytest.mark.asyncio
async def test_persistence_integration():
    mock_store = AsyncMock(spec=SessionStore)
    mock_store.create = AsyncMock()
    mock_store.delete = AsyncMock()

    manager = SessionManager(session_store=mock_store)
    session = await manager.create(title="Persist Session", provider="openai", model="gpt-4o")

    mock_store.create.assert_called_once_with(
        title="Persist Session",
        provider="openai",
        model="gpt-4o",
        session_id=session.id,
    )

    result = await manager.remove(session.id)
    assert result is True
    mock_store.delete.assert_called_once_with(session.id)


@pytest.mark.asyncio
async def test_no_persistence_without_store():
    manager = SessionManager()
    session = await manager.create(title="Test")

    assert session.id is not None
    result = await manager.remove(session.id)
    assert result is True
