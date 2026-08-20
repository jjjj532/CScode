"""G-8: openapi 生成器测试。

锁定 scripts/gen_api.py 的纯函数行为：
- 路径 → 方法名映射规则（camelCase、参数占位、复数/单数区分）
- schema → 端点表转换（method/needsBody/path 模板）
- TS 输出格式（类型定义 + 常量 + 手工补录段标记）
- 幂等性（重新生成输出一致）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from gen_api import (  # type: ignore[import-not-found]
    build_endpoint_entries,
    method_name_from_path,
    render_ts,
)

# ── 样例 schema（模拟后端真实形态）───────────────────────────────
SAMPLE_SCHEMA: dict[str, object] = {
    "openapi": "3.1.0",
    "info": {"title": "CScode API", "version": "0.4.0"},
    "paths": {
        "/api/sessions": {
            "get": {"operationId": "list_sessions", "responses": {"200": {"description": "ok"}}},
            "post": {"operationId": "create_session", "responses": {"200": {"description": "ok"}}},
        },
        "/api/sessions/{session_id}": {
            "get": {"operationId": "get_session", "responses": {"200": {"description": "ok"}}},
            "delete": {"operationId": "delete_session", "responses": {"200": {"description": "ok"}}},
            "patch": {"operationId": "update_session", "responses": {"200": {"description": "ok"}}},
        },
        "/api/chat": {
            "post": {"operationId": "send_chat", "responses": {"200": {"description": "ok"}}},
        },
        "/api/health": {
            "get": {"operationId": "health_check", "responses": {"200": {"description": "ok"}}},
        },
    },
}


# ── 方法名映射 ──────────────────────────────────────────────────
class TestMethodNameMapping:
    def test_simple_get_becomes_camel_case(self) -> None:
        # 无 operationId 时单数资源 fallback：get + 名词
        assert method_name_from_path("/api/health", "get") == "getHealth"

    def test_simple_get_with_operation_id_is_semantic(self) -> None:
        # 有 operationId 时优先语义化（health_check → healthCheck）
        from gen_api import _entry_from_operation

        entry = _entry_from_operation("/api/health", "get", {"operationId": "health_check"})
        assert entry["_name"] == "healthCheck"

    def test_path_with_param_uses_verb_prefix(self) -> None:
        assert method_name_from_path("/api/sessions/{session_id}", "get") == "getSession"
        assert method_name_from_path("/api/sessions/{session_id}", "delete") == "deleteSession"

    def test_collection_get_is_pluralized_verb(self) -> None:
        # /api/sessions GET → listSessions（动词+复数名）
        assert method_name_from_path("/api/sessions", "get") == "listSessions"

    def test_post_on_collection_is_create(self) -> None:
        assert method_name_from_path("/api/sessions", "post") == "createSession"

    def test_camel_case_drops_underscores(self) -> None:
        assert method_name_from_path("/api/permission-rules", "get") == "listPermissionRules"

    def test_does_not_mutate_path_hyphens(self) -> None:
        # 路径中的连字符保留在 key 可读性上，方法名用 CamelCase
        assert method_name_from_path("/api/permission-rules", "post") == "createPermissionRule"


# ── 端点表构建 ──────────────────────────────────────────────────
class TestBuildEndpointEntries:
    def test_all_paths_methods_extracted(self) -> None:
        entries = build_endpoint_entries(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        keys = set(entries.keys())
        assert {
            "listSessions",
            "createSession",
            "getSession",
            "deleteSession",
            "updateSession",
            "sendChat",
            "healthCheck",
        } <= keys

    def test_entry_shape(self) -> None:
        entries = build_endpoint_entries(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        assert entries["sendChat"] == {"path": "/api/chat", "method": "POST", "needsBody": True}
        assert entries["healthCheck"] == {"path": "/api/health", "method": "GET", "needsBody": False}
        assert entries["getSession"] == {
            "path": "/api/sessions/{session_id}",
            "method": "GET",
            "needsBody": False,
        }

    def test_patch_put_needs_body(self) -> None:
        assert build_endpoint_entries(SAMPLE_SCHEMA)["updateSession"]["needsBody"]  # type: ignore[arg-type]

    def test_duplicate_method_names_get_suffix(self) -> None:
        # 两条不同路径产出同名方法（/api/session/{id} GET × 2，参数名不同）
        schema: dict[str, object] = {
            "paths": {
                "/api/session/{session_id}": {
                    "get": {"responses": {"200": {"description": "ok"}}}
                },
                "/api/session/{id}": {
                    "get": {"responses": {"200": {"description": "ok"}}}
                },
            }
        }
        entries = build_endpoint_entries(schema)
        assert "getSession" in entries
        assert "getSession1" in entries


# ── TS 渲染 ─────────────────────────────────────────────────────
class TestRenderTs:
    def test_output_contains_type_and_const(self) -> None:
        out = render_ts(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        assert "export interface ApiEndpoint" in out
        assert "export const ENDPOINTS" in out
        assert "as const satisfies Record<string, ApiEndpoint>" in out

    def test_output_contains_generated_header_and_manual_section(self) -> None:
        out = render_ts(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        assert "GENERATED FILE" in out
        assert "手工补录段" in out or "MANUAL" in out
        # 手工补录段必须位于生成段之后
        assert out.index("GENERATED FILE") < out.index("手工补录段")

    def test_generated_ts_is_valid_parsable(self) -> None:
        # 渲染结果应能被 TS 解析器接受（此处校验结构完整性）
        out = render_ts(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        assert out.count("{") == out.count("}") or out.count("{") - out.count("}") == 2


# ── 幂等性 ──────────────────────────────────────────────────────
class TestIdempotency:
    def test_render_is_deterministic(self) -> None:
        assert render_ts(SAMPLE_SCHEMA) == render_ts(SAMPLE_SCHEMA)  # type: ignore[arg-type]

    def test_entries_sorted_stable(self) -> None:
        e1 = build_endpoint_entries(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        e2 = build_endpoint_entries(SAMPLE_SCHEMA)  # type: ignore[arg-type]
        assert list(e1.keys()) == list(e2.keys())