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

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from cscode.storage.db import Database
from cscode.utils.logging import get_logger

logger = get_logger(__name__)


# ─── Types ─────────────────────────────────────────────────────────


class RuleEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class ReplyMode(StrEnum):
    """Tri-state user reply to a pending permission request (spec §5.3).

    - ONCE:   allow this one request only (no persistence).
    - ALWAYS: remember the decision — persist an ALLOW rule.
    - REJECT: deny and record the decision.
    """

    ONCE = "once"
    ALWAYS = "always"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    """A queued permission request awaiting a user reply."""

    request_id: str
    session_id: str
    action: str
    resource: str


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
    session_id TEXT,
    action TEXT NOT NULL DEFAULT '*',
    resource TEXT NOT NULL DEFAULT '*',
    effect TEXT NOT NULL DEFAULT 'deny',
    created_at REAL NOT NULL DEFAULT (julianday('now'))
)
"""


class SavedRules:
    """Persistent rule storage backed by the application database.

    Supports both global rules (session_id=NULL) and session-scoped rules.
    Session rules take precedence over global rules during evaluation.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def _ensure_table(self) -> None:
        await self._db.conn.execute(_SAVED_RULES_TABLE)

    # ── Global rules ────────────────────────────────────────────────

    async def save(self, rule: Rule) -> int:
        """Persist a global rule (applies to all sessions). Returns the new row id."""
        logger.debug("SavedRules.save: %s/%s -> %s", rule.action, rule.resource, rule.effect)
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "INSERT INTO saved_rules (action, resource, effect) VALUES (?, ?, ?)",
            (rule.action, rule.resource, rule.effect.value),
        )
        await self._db.conn.commit()
        assert cursor.lastrowid is not None, "INSERT should return a row id"
        return cursor.lastrowid

    async def load(self) -> list[Rule]:
        """Load all global rules (session_id IS NULL)."""
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "SELECT action, resource, effect FROM saved_rules WHERE session_id IS NULL ORDER BY id ASC"
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
        """Remove all saved rules (global and session-level)."""
        logger.debug("SavedRules.clear")
        await self._ensure_table()
        await self._db.conn.execute("DELETE FROM saved_rules")
        await self._db.conn.commit()

    # ── Session-scoped rules ────────────────────────────────────────

    async def save_session_rule(self, session_id: str, rule: Rule) -> int:
        """Save a rule scoped to a specific session. Returns the new row id."""
        logger.debug("SavedRules.save_session_rule: session=%s %s/%s -> %s",
                     session_id, rule.action, rule.resource, rule.effect)
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "INSERT INTO saved_rules (session_id, action, resource, effect) VALUES (?, ?, ?, ?)",
            (session_id, rule.action, rule.resource, rule.effect.value),
        )
        await self._db.conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def load_session_rules(self, session_id: str) -> list[Rule]:
        """Load all rules scoped to a specific session."""
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "SELECT action, resource, effect FROM saved_rules WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
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

    async def clear_session_rules(self, session_id: str) -> None:
        """Remove all rules for a specific session."""
        logger.debug("SavedRules.clear_session_rules: session=%s", session_id)
        await self._ensure_table()
        await self._db.conn.execute(
            "DELETE FROM saved_rules WHERE session_id = ?", (session_id,)
        )
        await self._db.conn.commit()

    async def load_all(self) -> list[tuple[str | None, Rule]]:
        """Load all rules (global + session) with their session_id."""
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "SELECT session_id, action, resource, effect FROM saved_rules ORDER BY id ASC"
        )
        rows = await cursor.fetchall()
        return [
            (row["session_id"], Rule(
                action=row["action"],
                resource=row["resource"],
                effect=RuleEffect(row["effect"]),
            ))
            for row in rows
        ]

    async def list_all(self) -> list[dict[str, object]]:
        """Load all rules with their database id for API consumption.

        Returns dicts with keys: id, session_id, action, resource, effect.
        """
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "SELECT id, session_id, action, resource, effect FROM saved_rules ORDER BY id ASC"
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "action": row["action"],
                "resource": row["resource"],
                "effect": row["effect"],
            }
            for row in rows
        ]

    # ── Individual rule CRUD ─────────────────────────────────────────

    async def delete_by_id(self, rule_id: int) -> None:
        """Delete a single rule by its id.

        Raises KeyError if no rule with that id exists.
        """
        logger.debug("SavedRules.delete_by_id: id=%d", rule_id)
        await self._ensure_table()
        cursor = await self._db.conn.execute(
            "DELETE FROM saved_rules WHERE id = ?", (rule_id,)
        )
        await self._db.conn.commit()
        if cursor.rowcount == 0:
            msg = f"Rule with id {rule_id} not found"
            raise KeyError(msg)

    async def update(
        self,
        rule_id: int,
        *,
        action: str | None = None,
        resource: str | None = None,
        effect: RuleEffect | None = None,
    ) -> None:
        """Update fields of an existing rule.

        Only non-None keyword arguments are applied. Raises KeyError
        if no rule with that id exists.
        """
        logger.debug("SavedRules.update: id=%d", rule_id)
        await self._ensure_table()

        fields: list[str] = []
        params: list[object] = []
        if action is not None:
            fields.append("action = ?")
            params.append(action)
        if resource is not None:
            fields.append("resource = ?")
            params.append(resource)
        if effect is not None:
            fields.append("effect = ?")
            params.append(effect.value)

        if not fields:
            return  # nothing to update

        params.append(rule_id)
        cursor = await self._db.conn.execute(
            f"UPDATE saved_rules SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        await self._db.conn.commit()
        if cursor.rowcount == 0:
            msg = f"Rule with id {rule_id} not found"
            raise KeyError(msg)


class SessionPermission:
    """Session-level permission evaluator.

    Merges global rules and session-specific rules, evaluating them
    together with last-match-wins semantics. Session rules are evaluated
    AFTER global rules, giving them higher priority.
    """

    def __init__(self, saved_rules: SavedRules) -> None:
        self._saved_rules = saved_rules
        self._pending: dict[str, PermissionRequest] = {}

    async def evaluate(
        self,
        session_id: str,
        action: str,
        resource: str,
    ) -> Rule | None:
        """Evaluate action+resource for a specific session.

        Global rules are evaluated first, then session-level rules
        override them (last-match-wins).
        """
        all_rules = await self._saved_rules.load_all()
        # Build rulesets: global first, then session-specific
        global_rules = Ruleset(name="global", rules=[
            rule for sid, rule in all_rules if sid is None
        ])
        session_rules = Ruleset(name=f"session:{session_id}", rules=[
            rule for sid, rule in all_rules if sid == session_id
        ])
        return PermissionV2.evaluate(action, resource, [global_rules, session_rules])

    async def is_allowed(
        self,
        session_id: str,
        action: str,
        resource: str,
        remember: bool = False,
    ) -> bool:
        """Return True if the request is allowed under saved rules.

        ``remember=True`` only affects decisions made via ``reply(ALWAYS)``
        which persists the ALLOW rule; this method itself never writes.
        """
        rule = await self.evaluate(session_id, action, resource)
        return rule is not None and rule.effect == RuleEffect.ALLOW

    async def is_denied(self, session_id: str, action: str, resource: str) -> bool:
        rule = await self.evaluate(session_id, action, resource)
        return rule is not None and rule.effect == RuleEffect.DENY

    # ─── Tri-state queue (spec §5.3) ────────────────────────────────

    async def ask(self, session_id: str, action: str, resource: str) -> str:
        """Queue a permission request and return its request_id."""
        request_id = str(uuid.uuid4())
        self._pending[request_id] = PermissionRequest(
            request_id=request_id,
            session_id=session_id,
            action=action,
            resource=resource,
        )
        logger.debug(
            "Permission asked: request=%s session=%s action=%s resource=%s",
            request_id, session_id, action, resource,
        )
        return request_id

    async def reply(self, request_id: str, mode: ReplyMode) -> bool:
        """Resolve a pending request with a tri-state decision.

        ONCE: pop only (no persistence). ALWAYS: pop + persist ALLOW rule.
        REJECT: pop + persist DENY rule. Returns False for unknown id.
        """
        req = self._pending.pop(request_id, None)
        if req is None:
            logger.warning("Permission reply for unknown request: %s", request_id)
            return False

        if mode is ReplyMode.ALWAYS:
            await self._saved_rules.save_session_rule(
                req.session_id,
                Rule(action=req.action, resource=req.resource, effect=RuleEffect.ALLOW),
            )
        elif mode is ReplyMode.REJECT:
            await self._saved_rules.save_session_rule(
                req.session_id,
                Rule(action=req.action, resource=req.resource, effect=RuleEffect.DENY),
            )
        logger.info(
            "Permission resolved: request=%s mode=%s session=%s",
            request_id, mode.value, req.session_id,
        )
        return True

    async def list_pending(
        self, session_id: str | None = None
    ) -> list[PermissionRequest]:
        """Return queued requests, optionally filtered by session_id."""
        if session_id is None:
            return list(self._pending.values())
        return [r for r in self._pending.values() if r.session_id == session_id]
