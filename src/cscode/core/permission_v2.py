"""PermissionV2, Wildcard, and SavedRules for Phase 2 Core layer.

Architecture (from cscode-rearchitecture.md):
  PermissionV2.evaluate(action, resource, rulesets) -> Rule | None
    → Wildcard 匹配, last-match-wins

  Wildcard.match(pattern, value) -> bool
    → Supports *, **, ? patterns (filesystem-style glob)

  SavedRules:
    → Persist Rule objects to the event store database
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from cscode.storage.db import Database
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


# ─── Types ─────────────────────────────────────────────────────────


class RuleEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Rule:
    """A single permission rule.

    Attributes:
        action:  The action pattern (e.g. 'read', 'write', 'bash', '*').
        resource: The resource pattern (e.g. '/tmp/*', 'src/**/*.py', '*').
        effect:  allow or deny.
    """

    action: str = "*"
    resource: str = "*"
    effect: RuleEffect = RuleEffect.DENY


@dataclass
class Ruleset:
    """A named collection of rules."""

    name: str = ""
    rules: list[Rule] = field(default_factory=list)


# ─── Wildcard Matching ─────────────────────────────────────────────


class Wildcard:
    """Filesystem-style wildcard pattern matching.

    Supports:
        *   — matches any sequence of characters (except /)
        **  — matches any sequence including /
        ?   — matches any single character (including /)
    """

    @staticmethod
    def match(pattern: str, value: str) -> bool:
        """Return True if *value* matches the *pattern*.

        Uses recursive matching with index pointers for both
        the pattern and the value string.
        """
        return _wildcard_match(pattern, value)


def _wildcard_match(pattern: str, value: str) -> bool:
    """Recursive wildcard matcher.

    Supports:
        ?  — matches any single character
        *  — matches any sequence of characters except /
        ** — matches any sequence including /
    """
    if not pattern:
        return not value

    # ** (globstar) — matches sequences including /
    if len(pattern) >= 2 and pattern[:2] == "**":
        rest = pattern[2:]  # everything after **
        # **/ means "zero or more directory levels"
        if rest.startswith("/"):
            rest = rest[1:]  # consume the /
            # Try matching **/ against 0..len(value) characters followed by /
            # i must be at a directory boundary (i==0 or value[:i].endswith("/"))
            for i in range(len(value), -1, -1):
                if i > 0 and not value[:i].endswith("/"):
                    continue
                if _wildcard_match(rest, value[i:]):
                    return True
        else:
            # ** alone — match any sequence including /
            for i in range(len(value), -1, -1):
                if _wildcard_match(rest, value[i:]):
                    return True
        return False

    # * — matches any sequence of characters (including /)
    if pattern[0] == "*":
        rest = pattern[1:]
        for i in range(len(value), -1, -1):
            if _wildcard_match(rest, value[i:]):
                return True
        return False

    # ? — matches any single character
    if pattern[0] == "?":
        if not value:
            return False
        return _wildcard_match(pattern[1:], value[1:])

    # Literal character match
    if not value:
        return False
    if pattern[0] != value[0]:
        return False
    return _wildcard_match(pattern[1:], value[1:])


# ─── PermissionV2 ──────────────────────────────────────────────────


class PermissionV2:
    """Permission evaluator using wildcard matching with last-match-wins semantics.

    Usage:
        ruleset = Ruleset(name="base", rules=[
            Rule(action="*", resource="*", effect=RuleEffect.ALLOW),
            Rule(action="delete", resource="/data/*", effect=RuleEffect.DENY),
        ])
        result = PermissionV2.evaluate("delete", "/data/file", [ruleset])
        # → Rule(effect=DENY)
    """

    @staticmethod
    def evaluate(
        action: str,
        resource: str,
        rulesets: list[Ruleset],
    ) -> Rule | None:
        """Evaluate an action+resource against a list of rulesets.

        Rules from all rulesets are flattened in order.
        Returns the **last** matching rule, or None if no rule matches.
        """
        last_match: Rule | None = None

        for ruleset in rulesets:
            for rule in ruleset.rules:
                if Wildcard.match(rule.action, action) and Wildcard.match(rule.resource, resource):
                    last_match = rule

        return last_match

    @staticmethod
    def is_allowed(
        action: str,
        resource: str,
        rulesets: list[Ruleset],
    ) -> bool:
        """Convenience: True if the last matching rule is ALLOW."""
        rule = PermissionV2.evaluate(action, resource, rulesets)
        return rule is not None and rule.effect == RuleEffect.ALLOW

    @staticmethod
    def is_denied(
        action: str,
        resource: str,
        rulesets: list[Ruleset],
    ) -> bool:
        """Convenience: True if the last matching rule is DENY."""
        rule = PermissionV2.evaluate(action, resource, rulesets)
        return rule is not None and rule.effect == RuleEffect.DENY


# ─── SavedRules persistence ────────────────────────────────────────


_SAVED_RULES_TABLE = """
CREATE TABLE IF NOT EXISTS saved_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL DEFAULT '*',
    resource TEXT NOT NULL DEFAULT '*',
    effect TEXT NOT NULL DEFAULT 'deny',
    created_at REAL NOT NULL DEFAULT (julianday('now'))
)
"""


class SavedRules:
    """Persistent rule storage backed by the application database.

    Rules are serialized as rows in the saved_rules table.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def _ensure_table(self) -> None:
        await self._db.conn.execute(_SAVED_RULES_TABLE)

    async def save(self, rule: Rule) -> None:
        """Persist a single rule."""
        logger.debug("SavedRules.save: %s/%s -> %s", rule.action, rule.resource, rule.effect)
        await self._ensure_table()
        await self._db.conn.execute(
            "INSERT INTO saved_rules (action, resource, effect) VALUES (?, ?, ?)",
            (rule.action, rule.resource, rule.effect.value),
        )
        await self._db.conn.commit()

    async def load(self) -> list[Rule]:
        """Load all persisted rules, in insertion order."""
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "SELECT action, resource, effect FROM saved_rules ORDER BY id ASC"
        )
        rows = await cursor.fetchall()
        return [
            Rule(
                action=row["action"],
                resource=row["resource"],
                effect=RuleEffect(row["effect"]),
            )
            for row in rows
        ]

    async def clear(self) -> None:
        """Remove all saved rules."""
        logger.debug("SavedRules.clear")
        await self._ensure_table()
        await self._db.conn.execute("DELETE FROM saved_rules")
        await self._db.conn.commit()
