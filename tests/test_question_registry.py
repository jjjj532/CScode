"""Unit tests for QuestionRegistry — async question/answer registry."""

from __future__ import annotations

import asyncio

import pytest

from cscode.server.question_registry import QuestionRegistry


@pytest.fixture
def registry() -> QuestionRegistry:
    return QuestionRegistry()


@pytest.mark.asyncio
async def test_register_and_resolve(registry: QuestionRegistry) -> None:
    """Register a question, resolve it, verify answers are delivered."""
    questions = [{"label": "Confirm?", "type": "boolean"}]
    task = asyncio.create_task(registry.register("s1", "tc1", questions))
    await asyncio.sleep(0)  # let register() acquire lock and create future

    pending = await registry.list_pending()
    assert len(pending) == 1
    request_id = pending[0]["request_id"]

    ok = await registry.resolve(request_id, ["yes"])
    assert ok is True

    answers = await task
    assert answers == ["yes"]


@pytest.mark.asyncio
async def test_reject_raises_cancelled_error(registry: QuestionRegistry) -> None:
    """Rejecting a question raises CancelledError in the waiter."""
    questions = [{"label": "Approve?", "type": "boolean"}]
    task = asyncio.create_task(registry.register("s2", "tc2", questions))
    await asyncio.sleep(0)

    pending = await registry.list_pending()
    request_id = pending[0]["request_id"]

    ok = await registry.reject(request_id)
    assert ok is True

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_resolve_unknown_returns_false(registry: QuestionRegistry) -> None:
    """Resolving a non-existent request_id returns False."""
    ok = await registry.resolve("nonexistent", ["no"])
    assert ok is False


@pytest.mark.asyncio
async def test_reject_unknown_returns_false(registry: QuestionRegistry) -> None:
    """Rejecting a non-existent request_id returns False."""
    ok = await registry.reject("nonexistent")
    assert ok is False


@pytest.mark.asyncio
async def test_resolve_already_resolved_returns_false(registry: QuestionRegistry) -> None:
    """Resolving an already-resolved request returns False."""
    questions = [{"label": "OK?"}]
    task = asyncio.create_task(registry.register("s3", "tc3", questions))
    await asyncio.sleep(0)

    pending = await registry.list_pending()
    request_id = pending[0]["request_id"]

    ok1 = await registry.resolve(request_id, ["a1"])
    assert ok1 is True
    await task  # drain

    # Second resolve should return False
    ok2 = await registry.resolve(request_id, ["a2"])
    assert ok2 is False


@pytest.mark.asyncio
async def test_reject_already_rejected_returns_false(registry: QuestionRegistry) -> None:
    """Rejecting an already-rejected request returns False."""
    questions = [{"label": "OK?"}]
    task = asyncio.create_task(registry.register("s4", "tc4", questions))
    await asyncio.sleep(0)

    pending = await registry.list_pending()
    request_id = pending[0]["request_id"]

    ok1 = await registry.reject(request_id)
    assert ok1 is True
    with pytest.raises(asyncio.CancelledError):
        await task

    # Second reject should return False
    ok2 = await registry.reject(request_id)
    assert ok2 is False


@pytest.mark.asyncio
async def test_list_pending_all(registry: QuestionRegistry) -> None:
    """list_pending returns all pending questions."""
    q1 = [{"label": "Q1"}]
    q2 = [{"label": "Q2"}]
    t1 = asyncio.create_task(registry.register("s1", "tc1", q1))
    t2 = asyncio.create_task(registry.register("s2", "tc2", q2))
    await asyncio.sleep(0)

    pending = await registry.list_pending()
    # Might be 1 or 2 depending on whether both tasks have registered
    # Both should complete their non-await part by now
    await asyncio.sleep(0)
    pending = await registry.list_pending()
    assert len(pending) == 2

    # Cleanup
    for p in pending:
        await registry.reject(p["request_id"])
    for t in (t1, t2):
        try:
            await t
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_list_pending_filter_by_session(registry: QuestionRegistry) -> None:
    """list_pending filters by session_id."""
    q1 = [{"label": "Q1"}]
    q2 = [{"label": "Q2"}]
    t1 = asyncio.create_task(registry.register("s1", "tc1", q1))
    t2 = asyncio.create_task(registry.register("s2", "tc2", q2))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    pending_s1 = await registry.list_pending(session_id="s1")
    assert len(pending_s1) == 1
    assert pending_s1[0]["session_id"] == "s1"

    # Cleanup
    for p in pending_s1:
        await registry.reject(p["request_id"])
    try:
        await t1
    except asyncio.CancelledError:
        pass

    pending_s2 = await registry.list_pending(session_id="s2")
    for p in pending_s2:
        await registry.reject(p["request_id"])
    try:
        await t2
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_cancel_session_cleans_up(registry: QuestionRegistry) -> None:
    """cancel_session cancels all questions for a session."""
    q1 = [{"label": "Q1"}]
    q2 = [{"label": "Q2"}]
    q3 = [{"label": "Q3"}]

    t1 = asyncio.create_task(registry.register("s1", "tc1", q1))
    t2 = asyncio.create_task(registry.register("s1", "tc2", q2))
    t3 = asyncio.create_task(registry.register("s2", "tc3", q3))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await registry.cancel_session("s1")

    # s1 tasks should raise CancelledError
    with pytest.raises(asyncio.CancelledError):
        await t1
    with pytest.raises(asyncio.CancelledError):
        await t2

    # s2 task should still be pending
    pending = await registry.list_pending()
    assert len(pending) == 1
    assert pending[0]["session_id"] == "s2"

    # Cleanup
    await registry.reject(pending[0]["request_id"])
    try:
        await t3
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_cancelled_during_register_cleans_up(registry: QuestionRegistry) -> None:
    """If the caller is cancelled while awaiting register(), the entry is removed."""
    task = asyncio.create_task(registry.register("s1", "tc1", [{"label": "?"}]))
    await asyncio.sleep(0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Entry should be cleaned up
    pending = await registry.list_pending()
    assert len(pending) == 0


@pytest.mark.asyncio
async def test_list_pending_empty(registry: QuestionRegistry) -> None:
    """list_pending returns empty list when no questions are pending."""
    pending = await registry.list_pending()
    assert pending == []


@pytest.mark.asyncio
async def test_register_metadata_in_list(registry: QuestionRegistry) -> None:
    """list_pending entries include session_id, tool_call_id, questions."""
    questions = [{"label": "Test?", "type": "text"}]
    task = asyncio.create_task(registry.register("s1", "tc1", questions))
    await asyncio.sleep(0)

    pending = await registry.list_pending()
    assert len(pending) == 1
    entry = pending[0]
    assert entry["session_id"] == "s1"
    assert entry["tool_call_id"] == "tc1"
    assert entry["questions"] == questions
    assert "request_id" in entry

    # Cleanup
    await registry.reject(entry["request_id"])
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_cancel_session_empty_session(registry: QuestionRegistry) -> None:
    """cancel_session on a session with no questions is a no-op."""
    # Should not raise
    await registry.cancel_session("nonexistent")
    pending = await registry.list_pending()
    assert pending == []
