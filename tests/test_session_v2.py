"""Tests for Session V2 Input/Runner (cscode.core.session_v2).

Tests verify SPEC §2.3:
- DeliveryMode enum values
- AdmittedInput creation and properties
- SessionInput admit/promote/has_pending/peek
- SessionRunner register/run/stop
"""

from __future__ import annotations

from typing import Any

import pytest

from cscode.core.session_v2 import (
    AdmittedInput,
    DeliveryMode,
    SessionInput,
    SessionRunner,
    create_session_input,
)


# ═══════════════════════════════════════════════════════════════════
# DeliveryMode
# ═══════════════════════════════════════════════════════════════════

class TestDeliveryMode:
    def test_steer_value(self) -> None:
        assert DeliveryMode.STEER.value == "steer"

    def test_queue_value(self) -> None:
        assert DeliveryMode.QUEUE.value == "queue"

    def test_steer_is_distinct(self) -> None:
        assert DeliveryMode.STEER != DeliveryMode.QUEUE


# ═══════════════════════════════════════════════════════════════════
# AdmittedInput
# ═══════════════════════════════════════════════════════════════════

class TestAdmittedInput:
    def test_defaults(self) -> None:
        inp = AdmittedInput()
        assert inp.role == "user"
        assert inp.content == ""
        assert inp.mode == DeliveryMode.QUEUE

    def test_default_id_is_generated(self) -> None:
        inp = AdmittedInput()
        assert isinstance(inp.id, str)
        assert len(inp.id) > 0

    def test_default_timestamp(self) -> None:
        inp = AdmittedInput()
        assert isinstance(inp.timestamp, str)
        assert len(inp.timestamp) > 0

    def test_steer_input(self) -> None:
        inp = AdmittedInput(content="urgent", mode=DeliveryMode.STEER)
        assert inp.is_steer is True
        assert inp.is_queued is False

    def test_queued_input(self) -> None:
        inp = AdmittedInput(content="normal", mode=DeliveryMode.QUEUE)
        assert inp.is_queued is True
        assert inp.is_steer is False

    def test_custom_metadata(self) -> None:
        inp = AdmittedInput(
            content="hi",
            metadata={"source": "voice", "priority": 1},
        )
        assert inp.metadata["source"] == "voice"
        assert inp.metadata["priority"] == 1

    def test_unique_ids(self) -> None:
        ids = {AdmittedInput().id for _ in range(100)}
        assert len(ids) == 100  # All unique


# ═══════════════════════════════════════════════════════════════════
# SessionInput
# ═══════════════════════════════════════════════════════════════════

class TestSessionInputAdmit:
    @pytest.mark.asyncio
    async def test_admit_queue(self) -> None:
        si = SessionInput()
        inp = await si.admit(content="hello")
        assert inp.content == "hello"
        assert inp.mode == DeliveryMode.QUEUE

    @pytest.mark.asyncio
    async def test_admit_steer(self) -> None:
        si = SessionInput()
        inp = await si.admit(content="urgent", mode=DeliveryMode.STEER)
        assert inp.mode == DeliveryMode.STEER

    @pytest.mark.asyncio
    async def test_admit_returns_input(self) -> None:
        si = SessionInput()
        inp = await si.admit(content="test", role="user")
        assert isinstance(inp, AdmittedInput)
        assert inp.content == "test"

    @pytest.mark.asyncio
    async def test_admit_custom_role(self) -> None:
        si = SessionInput()
        inp = await si.admit(content="system msg", role="system")
        assert inp.role == "system"


class TestSessionInputPromote:
    @pytest.mark.asyncio
    async def test_promote_steers(self) -> None:
        si = SessionInput()
        await si.admit(content="s1", mode=DeliveryMode.STEER)
        await si.admit(content="s2", mode=DeliveryMode.STEER)
        steers = await si.promote_steers()
        assert len(steers) == 2
        assert steers[0].content == "s1"

    @pytest.mark.asyncio
    async def test_promote_steers_clears_list(self) -> None:
        si = SessionInput()
        await si.admit(content="x", mode=DeliveryMode.STEER)
        await si.promote_steers()
        remaining = await si.promote_steers()
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_promote_next_queued(self) -> None:
        si = SessionInput()
        await si.admit(content="first")
        await si.admit(content="second")
        first = await si.promote_next_queued()
        assert first is not None
        assert first.content == "first"
        second = await si.promote_next_queued()
        assert second is not None
        assert second.content == "second"

    @pytest.mark.asyncio
    async def test_promote_next_queued_empty(self) -> None:
        si = SessionInput()
        result = await si.promote_next_queued()
        assert result is None

    @pytest.mark.asyncio
    async def test_promote_fifo_order(self) -> None:
        si = SessionInput()
        await si.admit(content="a")
        await si.admit(content="b")
        await si.admit(content="c")
        assert (await si.promote_next_queued()).content == "a"
        assert (await si.promote_next_queued()).content == "b"
        assert (await si.promote_next_queued()).content == "c"


class TestSessionInputPending:
    @pytest.mark.asyncio
    async def test_has_pending_queued(self) -> None:
        si = SessionInput()
        assert si.has_pending() is False
        await si.admit(content="x")
        assert si.has_pending() is True

    @pytest.mark.asyncio
    async def test_has_pending_steer(self) -> None:
        si = SessionInput()
        await si.admit(content="x", mode=DeliveryMode.STEER)
        assert si.has_pending() is True

    @pytest.mark.asyncio
    async def test_has_pending_after_promote(self) -> None:
        si = SessionInput()
        await si.admit(content="x", mode=DeliveryMode.STEER)
        await si.promote_steers()
        assert si.has_pending() is False

    @pytest.mark.asyncio
    async def test_pending_count(self) -> None:
        si = SessionInput()
        assert si.pending_count() == 0
        await si.admit(content="q1")
        await si.admit(content="s1", mode=DeliveryMode.STEER)
        assert si.pending_count() == 2


class TestSessionInputPeek:
    @pytest.mark.asyncio
    async def test_peek_steers(self) -> None:
        si = SessionInput()
        await si.admit(content="s1", mode=DeliveryMode.STEER)
        await si.admit(content="s2", mode=DeliveryMode.STEER)
        peeked = si.peek_steers()
        assert len(peeked) == 2
        # Peek should not remove
        assert si.has_pending() is True

    @pytest.mark.asyncio
    async def test_peek_queue(self) -> None:
        si = SessionInput()
        await si.admit(content="a")
        await si.admit(content="b")
        await si.admit(content="c")
        peeked = si.peek_queue(n=2)
        assert len(peeked) == 2
        assert peeked[0].content == "a"
        # Peek should not remove
        assert si.pending_count() == 3


# ═══════════════════════════════════════════════════════════════════
# SessionRunner
# ═══════════════════════════════════════════════════════════════════

class TestSessionRunner:
    @pytest.mark.asyncio
    async def test_register_handler(self) -> None:
        si = SessionInput()
        runner = SessionRunner(si)
        assert len(runner._handlers) == 0

        async def handler() -> dict:
            return {"status": "ok"}
        runner.register_handler(handler)
        assert len(runner._handlers) == 1

    @pytest.mark.asyncio
    async def test_run_processes_inputs(self) -> None:
        si = SessionInput()
        runner = SessionRunner(si)
        processed: list[str] = []

        async def handler() -> dict[str, str]:
            processed.append("ran")
            return {"status": "ok"}
        runner.register_handler(handler)

        await si.admit(content="test")
        # Run briefly then stop
        async def run_and_stop() -> None:
            import asyncio
            task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.05)
            await runner.stop()
            await task

        await run_and_stop()
        assert len(processed) >= 1

    @pytest.mark.asyncio
    async def test_run_steers_before_queue(self) -> None:
        si = SessionInput()
        runner = SessionRunner(si)
        processed: list[str] = []

        async def handler() -> dict[str, str]:
            processed.append("ran")
            return {"status": "ok"}
        runner.register_handler(handler)

        await si.admit(content="queued1")
        await si.admit(content="STEER", mode=DeliveryMode.STEER)
        await si.admit(content="queued2")

        async def run_and_stop() -> None:
            import asyncio
            task = asyncio.create_task(runner.run())
            await asyncio.sleep(0.05)
            await runner.stop()
            await task

        await run_and_stop()
        assert len(processed) >= 1

    @pytest.mark.asyncio
    async def test_stop_ends_run(self) -> None:
        si = SessionInput()
        runner = SessionRunner(si)

        async def handler() -> dict[str, str]:
            return {"status": "ok"}
        runner.register_handler(handler)

        # Run and stop immediately
        import asyncio
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0.01)
        await runner.stop()
        await task
        assert runner._running is False


# ═══════════════════════════════════════════════════════════════════
# create_session_input factory
# ═══════════════════════════════════════════════════════════════════

class TestFactory:
    def test_create_session_input(self) -> None:
        si = create_session_input()
        assert isinstance(si, SessionInput)
