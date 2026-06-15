from __future__ import annotations

from dataclasses import dataclass

from cscode.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PolicyRule:
    name: str
    target: str  # format: "tool:ToolName" or "resource:path"
    action: str  # "allow", "deny", "ask"
    priority: int = 0

    def matches(self, category: str, identifier: str) -> bool:
        expected = f"{category}:{identifier}"
        return self.target == expected


class PolicyEngine:
    def __init__(self) -> None:
        self._rules: dict[str, PolicyRule] = {}

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules[rule.name] = rule
        logger.info("Policy: added rule '%s' (%s -> %s)", rule.name, rule.target, rule.action)

    def remove_rule(self, name: str) -> None:
        self._rules.pop(name, None)

    def evaluate(self, category: str, identifier: str) -> str:
        for rule in sorted(self._rules.values(), key=lambda r: -r.priority):
            if rule.matches(category, identifier):
                return rule.action
        return "allow"

    def list_rules(self) -> list[PolicyRule]:
        return list(self._rules.values())
