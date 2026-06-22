from __future__ import annotations
import asyncio
import pytest
from cscode.server.coordinator import SessionCoordinator


@pytest.mark.asyncio
async def test_run_sequential():
    c = SessionCoordinator()
    order = []
    async def slow():
        order.append("start")
        await asyncio.sleep(0.05)
        order.append("end")
    await c.run("s", slow)
    assert order == ["start", "end"]


@pytest.mark.asyncio
async def test_run_waits_for_previous():
    c = SessionCoordinator()
    order = []
    async def slow():
        order.append("start")
        await asyncio.sleep(0.1)
        order.append("end")
    t1 = asyncio.create_task(c.run("s", slow))
    await asyncio.sleep(0.02)
    t2 = asyncio.create_task(c.run("s", slow))
    await asyncio.gather(t1, t2)
    assert order == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_wake_coalesces():
    c = SessionCoordinator()
    order = []
    async def slow():
        order.append("start")
        await asyncio.sleep(0.05)
        order.append("end")
    t1 = asyncio.create_task(c.wake("s", slow))
    await asyncio.sleep(0.01)
    asyncio.create_task(c.wake("s", slow))
    await asyncio.sleep(0.01)
    asyncio.create_task(c.wake("s", slow))
    await t1
    assert order == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_different_sessions_independent():
    c = SessionCoordinator()
    order = []
    async def make_handler(name: str):
        async def h():
            order.append(f"{name}_start")
            await asyncio.sleep(0.05)
            order.append(f"{name}_end")
        return h
    h1 = await make_handler("a")
    h2 = await make_handler("b")
    await asyncio.gather(c.run("a", h1), c.run("b", h2))
    assert order == ["a_start", "b_start", "a_end", "b_end"] or \
           order == ["b_start", "a_start", "b_end", "a_end"]
