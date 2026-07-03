"""TDD tests for PermissionV2, Wildcard, and SavedRules.

These tests are written FIRST (TDD). They MUST fail initially,
then pass after the implementation in core/permission_v2.py.
"""

from __future__ import annotations

import pytest

from cscode.core.permission_v2 import (
    PermissionV2,
    Rule,
    RuleEffect,
    Ruleset,
    SavedRules,
    Wildcard,
)

# ─── Wildcard.match — simple patterns ──────────────────────────────

class TestWildcardExact:
    def test_exact_match(self) -> None:
        assert Wildcard.match("read", "read") is True

    def test_exact_mismatch(self) -> None:
        assert Wildcard.match("read", "write") is False


class TestWildcardStar:
    def test_star_matches_all(self) -> None:
        assert Wildcard.match("*", "anything") is True

    def test_star_matches_empty(self) -> None:
        assert Wildcard.match("*", "") is True

    def test_prefix_star(self) -> None:
        assert Wildcard.match("*.py", "main.py") is True
        assert Wildcard.match("*.py", "main.txt") is False

    def test_suffix_star(self) -> None:
        assert Wildcard.match("read*", "read") is True
        assert Wildcard.match("read*", "read_file") is True
        assert Wildcard.match("read*", "write") is False

    def test_middle_star(self) -> None:
        assert Wildcard.match("a*c", "abc") is True
        assert Wildcard.match("a*c", "abbc") is True
        assert Wildcard.match("a*c", "ac") is True
        assert Wildcard.match("a*c", "ab") is False

    def test_multiple_stars(self) -> None:
        assert Wildcard.match("a*b*c", "aXbYc") is True
        assert Wildcard.match("a*b*c", "abc") is True
        assert Wildcard.match("a*b*c", "abXc") is True


class TestWildcardQuestion:
    def test_question_single_char(self) -> None:
        assert Wildcard.match("file.??", "file.py") is True  # 'py' is 2 chars
        assert Wildcard.match("file.??", "file.txt") is False  # 'txt' is 3 chars

    def test_question_with_star(self) -> None:
        assert Wildcard.match("file.???", "file.txt") is True
        assert Wildcard.match("file.???", "file.ab") is False  # only 2 chars after dot

    def test_question_at_start(self) -> None:
        assert Wildcard.match("?at", "cat") is True
        assert Wildcard.match("?at", "at") is False


class TestWildcardGlobstar:
    def test_doublestar_matches_across_dirs(self) -> None:
        assert Wildcard.match("src/**/*.py", "src/main.py") is True
        assert Wildcard.match("src/**/*.py", "src/a/b/c/file.py") is True
        assert Wildcard.match("src/**/*.py", "README.md") is False

    def test_doublestar_at_root(self) -> None:
        assert Wildcard.match("**/*", "any/path/file.txt") is True

    def test_single_star_crosses_dir(self) -> None:
        # In permission context, * matches across directory boundaries
        assert Wildcard.match("src/*.py", "src/main.py") is True
        assert Wildcard.match("src/*.py", "src/sub/file.py") is True


class TestWildcardSpecialChars:
    def test_dot_is_literal(self) -> None:
        assert Wildcard.match("config.json", "configXjson") is False

    def test_question_matches_dot(self) -> None:
        assert Wildcard.match("config.?son", "config.json") is True


# ─── PermissionV2.evaluate ─────────────────────────────────────────

class TestPermissionV2Evaluate:
    def test_single_rule_allows(self) -> None:
        ruleset = Ruleset(name="test", rules=[
            Rule(action="read", resource="*", effect=RuleEffect.ALLOW),
        ])
        result = PermissionV2.evaluate("read", "/tmp/x", [ruleset])
        assert result is not None
        assert result.effect == RuleEffect.ALLOW

    def test_single_rule_denies(self) -> None:
        ruleset = Ruleset(name="test", rules=[
            Rule(action="write", resource="*", effect=RuleEffect.DENY),
        ])
        result = PermissionV2.evaluate("write", "/etc/passwd", [ruleset])
        assert result is not None
        assert result.effect == RuleEffect.DENY

    def test_no_match_returns_none(self) -> None:
        ruleset = Ruleset(name="test", rules=[
            Rule(action="read", resource="/tmp/*", effect=RuleEffect.ALLOW),
        ])
        result = PermissionV2.evaluate("write", "/tmp/x", [ruleset])
        assert result is None

    def test_last_match_wins_order(self) -> None:
        """Last matching rule wins (not first)."""
        ruleset = Ruleset(name="test", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
            Rule(action="delete", resource="*", effect=RuleEffect.DENY),
        ])
        # delete is denied because the deny rule comes after allow
        result = PermissionV2.evaluate("delete", "/data", [ruleset])
        assert result is not None
        assert result.effect == RuleEffect.DENY

    def test_first_rule_allows_delete(self) -> None:
        """If deny comes first and allow later, allow wins (last-match)."""
        ruleset = Ruleset(name="test", rules=[
            Rule(action="delete", resource="*", effect=RuleEffect.DENY),
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
        ])
        result = PermissionV2.evaluate("delete", "/data", [ruleset])
        assert result is not None
        assert result.effect == RuleEffect.ALLOW

    def test_multiple_rulesets_scanned_in_order(self) -> None:
        """Multiple rulesets: rules are flattened in order."""
        rs1 = Ruleset(name="base", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
        ])
        rs2 = Ruleset(name="override", rules=[
            Rule(action="bash", resource="*", effect=RuleEffect.DENY),
        ])
        result = PermissionV2.evaluate("bash", "ls", [rs1, rs2])
        assert result is not None
        assert result.effect == RuleEffect.DENY

    def test_wildcard_action_and_resource(self) -> None:
        # Default-deny with specific allow override
        ruleset = Ruleset(name="test", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.DENY),
            Rule(action="*", resource="/safe/*", effect=RuleEffect.ALLOW),
        ])
        safe = PermissionV2.evaluate("read", "/safe/file.txt", [ruleset])
        unsafe = PermissionV2.evaluate("read", "/etc/passwd", [ruleset])
        assert safe is not None and safe.effect == RuleEffect.ALLOW
        assert unsafe is not None and unsafe.effect == RuleEffect.DENY

    def test_default_allow_with_specific_deny(self) -> None:
        """Default-allow with deny override (last-match-wins)."""
        ruleset = Ruleset(name="test", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
            Rule(action="*", resource="/secret/*", effect=RuleEffect.DENY),
        ])
        open_ = PermissionV2.evaluate("read", "/public/file", [ruleset])
        secret = PermissionV2.evaluate("read", "/secret/data", [ruleset])
        assert open_ is not None and open_.effect == RuleEffect.ALLOW
        assert secret is not None and secret.effect == RuleEffect.DENY


# ─── PermissionV2 convenience methods ──────────────────────────────

class TestPermissionV2Helpers:
    def test_is_allowed_simple(self) -> None:
        ruleset = Ruleset(name="t", rules=[
            Rule(action="read", resource="*", effect=RuleEffect.ALLOW),
        ])
        assert PermissionV2.is_allowed("read", "/any", [ruleset]) is True

    def test_is_allowed_denied(self) -> None:
        ruleset = Ruleset(name="t", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.DENY),
        ])
        assert PermissionV2.is_allowed("write", "/any", [ruleset]) is False

    def test_is_allowed_no_rule(self) -> None:
        ruleset = Ruleset(name="t", rules=[])
        assert PermissionV2.is_allowed("read", "/x", [ruleset]) is False


# ─── SavedRules ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_saved_rules_save_and_load() -> None:
    from cscode.storage.db import Database
    db = Database(":memory:")
    await db.init()

    store = SavedRules(db)
    rule = Rule(action="*", resource="/tmp/*", effect=RuleEffect.ALLOW)

    await store.save(rule)
    loaded = await store.load()

    assert len(loaded) == 1
    assert loaded[0].action == "*"
    assert loaded[0].resource == "/tmp/*"
    assert loaded[0].effect == RuleEffect.ALLOW


@pytest.mark.asyncio
async def test_saved_rules_multi_save_deduplicates() -> None:
    from cscode.storage.db import Database
    db = Database(":memory:")
    await db.init()

    store = SavedRules(db)
    r1 = Rule(action="read", resource="*", effect=RuleEffect.ALLOW)
    r2 = Rule(action="write", resource="/tmp/*", effect=RuleEffect.DENY)

    await store.save(r1)
    await store.save(r2)
    loaded = await store.load()

    assert len(loaded) == 2


@pytest.mark.asyncio
async def test_saved_rules_empty_db() -> None:
    from cscode.storage.db import Database
    db = Database(":memory:")
    await db.init()

    store = SavedRules(db)
    loaded = await store.load()
    assert loaded == []
