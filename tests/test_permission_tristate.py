"""Tests for G-7: Permission 三态 + 待处理队列 (spec §5.3).

Verifies the true gaps vs current permission_v2.py:
  - ReplyMode tri-state: once / always / reject
  - reply(request_id, mode) resolves pending requests
  - list_pending(session_id) returns queued permission requests
  - is_allowed(..., remember=True) persists ALWAYS decisions to SavedRules
  - ALWAYS rules survive session reload (persistence via SavedRules)
"""

from __future__ import annotations

import pytest

from cscode.core.permission_v2 import (
    PermissionRequest,
    ReplyMode,
    Rule,
    RuleEffect,
    SavedRules,
    SessionPermission,
)
from cscode.storage.db import Database

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db() -> Database:
    database = Database(":memory:")
    await database.init()
    return database


@pytest.fixture
async def saved(db: Database) -> SavedRules:
    return SavedRules(db)


@pytest.fixture
async def perms(saved: SavedRules) -> SessionPermission:
    return SessionPermission(saved_rules=saved)


class TestReplyMode:
    """验收标准 1: once 只放行本次；always 持久化；reject 拒绝并记录。"""

    async def test_reply_once_resolves_and_forgets(self, perms: SessionPermission) -> None:
        req_id = await perms.ask("s1", "bash", "ls -la")
        assert await perms.reply(req_id, ReplyMode.ONCE) is True
        # once 只放行本次——队列清空后该请求不再存在
        pending = await perms.list_pending()
        assert all(r.request_id != req_id for r in pending)
        # 不写入持久化规则
        rules = await perms._saved_rules.load_all()
        assert rules == []

    async def test_reply_always_writes_persistent_rule(self, perms: SessionPermission, db: Database) -> None:
        req_id = await perms.ask("s1", "bash", "*")
        assert await perms.reply(req_id, ReplyMode.ALWAYS) is True
        rules = await perms._saved_rules.load_all()
        assert len(rules) == 1
        _, rule = rules[0]
        assert rule.action == "bash"
        assert rule.effect == RuleEffect.ALLOW

    async def test_reply_reject_records_and_denies(self, perms: SessionPermission) -> None:
        req_id = await perms.ask("s1", "write", "/tmp/x")
        assert await perms.reply(req_id, ReplyMode.REJECT) is True
        # reject 后 is_allowed 返回 False（无 allow 规则）
        assert await perms.is_allowed("s1", "write", "/tmp/x") is False

    async def test_reply_unknown_request_id_returns_false(self, perms: SessionPermission) -> None:
        assert await perms.reply("no-such-id", ReplyMode.ONCE) is False


class TestPendingQueue:
    """验收标准 2: 待处理请求列表含 session_id/action/resource/request_id。"""

    async def test_ask_enqueues_request(self, perms: SessionPermission) -> None:
        req_id = await perms.ask("s1", "read", "/etc/hosts")
        pending = await perms.list_pending()
        assert len(pending) == 1
        req = pending[0]
        assert req.session_id == "s1"
        assert req.action == "read"
        assert req.resource == "/etc/hosts"
        assert req.request_id == req_id

    async def test_list_pending_filters_by_session(self, perms: SessionPermission) -> None:
        await perms.ask("s1", "read", "/a")
        await perms.ask("s2", "write", "/b")
        s1_pending = await perms.list_pending("s1")
        assert len(s1_pending) == 1
        assert s1_pending[0].session_id == "s1"
        assert len(await perms.list_pending()) == 2

    async def test_resolved_request_removed_from_queue(self, perms: SessionPermission) -> None:
        req_id = await perms.ask("s1", "bash", "*")
        await perms.reply(req_id, ReplyMode.REJECT)
        assert await perms.list_pending() == []


class TestAlwaysPersistence:
    """验收标准 3: always 规则在 session 重载后仍然生效（SavedRules 持久化）。"""

    async def test_always_survives_reload(
        self, saved: SavedRules
    ) -> None:
        # 第一次：always 决策写入规则表
        perms1 = SessionPermission(saved_rules=saved)
        req_id = await perms1.ask("s1", "bash", "*")
        await perms1.reply(req_id, ReplyMode.ALWAYS)

        # 重载：新实例从 SavedRules 读到规则（模拟 session reload）
        perms2 = SessionPermission(saved_rules=saved)
        assert await perms2.is_allowed("s1", "bash", "ls -la") is True

    async def test_is_allowed_remember_persists(
        self, saved: SavedRules
    ) -> None:
        perms = SessionPermission(saved_rules=saved)
        assert await perms.is_allowed("s1", "bash", "*", remember=True) is False
        # remember=True 但无规则时不应写任何东西（只有 ALWAYS 决策才写）
        rules = await saved.load_all()
        assert rules == []