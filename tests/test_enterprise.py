from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from cscode.enterprise.remote_config import RemoteConfigLoader
from cscode.enterprise.policies import PolicyEngine, PolicyRule
from cscode.enterprise.audit import AuditLogger, AuditEvent


class TestRemoteConfigLoader:
    def test_parse_well_known(self) -> None:
        data = {
            "provider": "openai",
            "model": "gpt-4o",
            "max_tokens": 8192,
            "permissions": {"Bash": "deny"},
        }
        config = RemoteConfigLoader.parse_config(data)
        assert config["provider"] == "openai"
        assert config["permissions"]["Bash"] == "deny"

    def test_parse_empty(self) -> None:
        config = RemoteConfigLoader.parse_config({})
        assert config == {}

    def test_load_from_file(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"provider": "azure", "model": "gpt-4"}, f)
            f.flush()
            config = RemoteConfigLoader.load_from_file(f.name)
            assert config["provider"] == "azure"
            Path(f.name).unlink(missing_ok=True)


class TestPolicyRule:
    def test_create_rule(self) -> None:
        rule = PolicyRule(
            name="block-bash",
            target="tool:Bash",
            action="deny",
        )
        assert rule.name == "block-bash"
        assert rule.target == "tool:Bash"
        assert rule.action == "deny"

    def test_matches_tool(self) -> None:
        rule = PolicyRule(name="block-bash", target="tool:Bash", action="deny")
        assert rule.matches("tool", "Bash")
        assert not rule.matches("tool", "Read")


class TestPolicyEngine:
    def test_add_and_evaluate(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(name="block-bash", target="tool:Bash", action="deny"))
        result = engine.evaluate("tool", "Bash")
        assert result == "deny"

    def test_default_allow(self) -> None:
        engine = PolicyEngine()
        result = engine.evaluate("tool", "Read")
        assert result == "allow"

    def test_remove_rule(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(name="block-bash", target="tool:Bash", action="deny"))
        engine.remove_rule("block-bash")
        assert engine.evaluate("tool", "Bash") == "allow"

    def test_list_rules(self) -> None:
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(name="r1", target="tool:Write", action="ask"))
        engine.add_rule(PolicyRule(name="r2", target="tool:Edit", action="deny"))
        rules = engine.list_rules()
        assert len(rules) == 2


class TestAuditLogger:
    def test_log_event(self) -> None:
        logger = AuditLogger()
        event = AuditEvent(
            action="tool.execute",
            actor="agent",
            target="Bash",
            details={"command": "ls"},
        )
        logger.log(event)
        events = logger.get_events()
        assert len(events) == 1
        assert events[0].action == "tool.execute"

    def test_filter_by_action(self) -> None:
        logger = AuditLogger()
        logger.log(AuditEvent(action="tool.execute", actor="agent", target="Read"))
        logger.log(AuditEvent(action="session.create", actor="user", target="s1"))
        logger.log(AuditEvent(action="tool.execute", actor="agent", target="Write"))

        filtered = logger.filter_by_action("tool.execute")
        assert len(filtered) == 2

    def test_clear(self) -> None:
        logger = AuditLogger()
        logger.log(AuditEvent(action="test", actor="a", target="t"))
        logger.clear()
        assert len(logger.get_events()) == 0
