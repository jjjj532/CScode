from __future__ import annotations

import json
import pytest
from cscode.sharing.serializer import SessionSerializer
from cscode.sharing.links import ShareLinkGenerator
from cscode.sharing.manager import ShareManager


class TestSessionSerializer:
    def test_serialize_session(self) -> None:
        serializer = SessionSerializer()
        session_data = {
            "id": "test-123",
            "title": "Test Session",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        }
        exported = serializer.export_json(session_data)
        assert isinstance(exported, str)
        parsed = json.loads(exported)
        assert parsed["id"] == "test-123"
        assert len(parsed["messages"]) == 2

    def test_import_json(self) -> None:
        serializer = SessionSerializer()
        data = json.dumps({"id": "imported-1", "title": "Imported", "messages": []})
        session = serializer.import_json(data)
        assert session["id"] == "imported-1"
        assert session["title"] == "Imported"

    def test_import_invalid_json(self) -> None:
        serializer = SessionSerializer()
        result = serializer.import_json("not valid json")
        assert result is None


class TestShareLinkGenerator:
    def test_generate_link(self) -> None:
        gen = ShareLinkGenerator(base_url="https://cscode.dev")
        link = gen.generate("session-abc")
        assert "session-abc" in link
        assert link.startswith("https://cscode.dev")

    def test_generate_link_with_token(self) -> None:
        gen = ShareLinkGenerator(base_url="https://cscode.dev")
        link = gen.generate("session-xyz", access_token="secret123")
        assert "token=secret123" in link

    def test_parse_link(self) -> None:
        gen = ShareLinkGenerator(base_url="https://cscode.dev")
        result = gen.parse("https://cscode.dev/share/session-abc?token=secret")
        assert result is not None
        assert result["session_id"] == "session-abc"
        assert result["token"] == "secret"


class TestShareManager:
    def test_create_share(self) -> None:
        mgr = ShareManager()
        share = mgr.create_share(session_id="s1", title="My Session")
        assert share["session_id"] == "s1"
        assert share["title"] == "My Session"
        assert "share_id" in share
        assert "created_at" in share

    def test_get_share(self) -> None:
        mgr = ShareManager()
        share = mgr.create_share(session_id="s1", title="Test")
        retrieved = mgr.get_share(share["share_id"])
        assert retrieved is not None
        assert retrieved["session_id"] == "s1"

    def test_get_nonexistent_share(self) -> None:
        mgr = ShareManager()
        assert mgr.get_share("nonexistent") is None

    def test_delete_share(self) -> None:
        mgr = ShareManager()
        share = mgr.create_share(session_id="s1", title="Test")
        assert mgr.delete_share(share["share_id"]) is True
        assert mgr.get_share(share["share_id"]) is None

    def test_list_shares(self) -> None:
        mgr = ShareManager()
        mgr.create_share(session_id="s1", title="A")
        mgr.create_share(session_id="s2", title="B")
        shares = mgr.list_shares()
        assert len(shares) == 2

    def test_set_visibility(self) -> None:
        mgr = ShareManager()
        share = mgr.create_share(session_id="s1", title="Test")
        mgr.set_visibility(share["share_id"], public=False)
        retrieved = mgr.get_share(share["share_id"])
        assert retrieved is not None
        assert retrieved["public"] is False
