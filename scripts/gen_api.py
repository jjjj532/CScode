#!/usr/bin/env python3
"""G-8: OpenAPI → TypeScript 端点表生成器。

从 FastAPI 的 OpenAPI schema 生成 `web/src/lib/api/generated/endpoints.ts`：
- 端点清单 + 方法名（camelCase）+ 路径模板 + needsBody
- 手工补录段（生成脚本不覆盖，用于 schema 缺失的前端实际调用端点，如 /api/session 单数别名）

用法：
    python scripts/gen_api.py [--schema schema.json] [--out endpoints.ts]
    # 无 --schema 时从 cscode.server.app 实时生成 schema

设计：纯函数（build_endpoint_entries / render_ts）可被 pytest 测试；
CLI 入口负责拉取 schema 与写文件。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# 需要 body 的 HTTP 方法
BODY_METHODS = {"POST", "PUT", "PATCH"}

# 复数名词 → 单数（用于 create 方法名）
_SINGULAR: dict[str, str] = {
    "sessions": "Session",
    "credentials": "Credential",
    "directories": "Directory",
    "jobs": "Job",
    "rules": "Rule",
    "agents": "Agent",
    "models": "Model",
    "providers": "Provider",
    "projects": "Project",
    "files": "File",
    "workspaces": "Workspace",
    "events": "Event",
    "logs": "Log",
}


def _singularize(noun: str) -> str:
    """复数名词 → 单数 CamelCase；不在表内时按词尾 s 规则回退。"""
    noun_lower = noun.lower()
    if noun_lower in _SINGULAR:
        return _SINGULAR[noun_lower]
    if noun_lower.endswith("s") and not noun_lower.endswith("ss"):
        return _camel(noun[:-1])
    return _camel(noun)


def _camel(segment: str) -> str:
    """下划线/连字符分段 → PascalCase 单词。"""
    return "".join(
        part[:1].upper() + part[1:] for part in re.split(r"[_-]+", segment) if part
    )


def _lower_camel(segment: str) -> str:
    """下划线/连字符分段 → lowerCamelCase（方法名用，首字母小写）。"""
    camel = _camel(segment)
    return camel[:1].lower() + camel[1:] if camel else camel


def method_name_from_path(path: str, http_method: str) -> str:
    """路径 + HTTP 方法 → 前端方法名（camelCase）。

    规则：
    - 无参数 GET + 复数末段 → list + 复数名词（listSessions）
    - 无参数 POST + 复数末段 → create + 单数名词（createSession）
    - 无参数 GET + 单数末段 → 动词 + 名词（healthCheck / configGet 由 operationId 兜底）
    - 带参数 GET → get + 名词（getSession）
    - 带参数 DELETE → delete + 名词（deleteSession）
    - 带参数 PATCH/PUT → update + 名词（updateSession）
    - 其他 POST（如 /api/chat）→ operationId 语义化（sendChat）
    """
    segments = [s for s in path.split("/") if s]
    has_param = "{" in path

    if has_param:
        noun = segments[-1] if "{" not in segments[-1] else segments[-2]
        noun_camel = _singularize(noun)
        if http_method.upper() == "GET":
            return f"get{noun_camel}"
        if http_method.upper() == "DELETE":
            return f"delete{noun_camel}"
        if http_method.upper() in {"PUT", "PATCH"}:
            return f"update{noun_camel}"
        return f"create{noun_camel}"

    noun = segments[-1] if segments else "root"
    noun_lower = noun.lower()
    is_plural_collection = noun_lower in _SINGULAR or noun_lower.endswith("s")
    if http_method.upper() == "GET" and is_plural_collection:
        return f"list{_camel(noun)}"
    if http_method.upper() == "POST" and is_plural_collection:
        return f"create{_singularize(noun)}"
    # 单数资源：动词前缀（get/update 等），由 operationId 精确化
    verb = {"GET": "get", "POST": "post", "PUT": "update", "PATCH": "update", "DELETE": "delete"}.get(
        http_method.upper(), "call"
    )
    return f"{verb}{_camel(noun)}"


def _entry_from_operation(path: str, http_method: str, op: dict[str, Any]) -> dict[str, str | bool]:
    """单 operation → 端点条目。operationId 存在时优先使用其语义化方法名。"""
    needs_body = http_method.upper() in BODY_METHODS
    name = method_name_from_path(path, http_method)
    op_id = op.get("operationId")
    if op_id:
        # FastAPI 默认 operationId = "{verb}_{path}_{method}"，截取 "_api_" 前缀作为语义名
        prefix = op_id.split("_api_", 1)[0]
        op_name = _lower_camel(prefix)
        if op_name:
            name = op_name
    return {"path": path, "method": http_method.upper(), "needsBody": needs_body, "_name": name}


def build_endpoint_entries(schema: dict[str, Any]) -> dict[str, dict[str, str | bool]]:
    """schema → { 方法名: {path, method, needsBody} }，排序稳定 + 冲突加后缀。"""
    entries: dict[str, dict[str, str | bool]] = {}
    paths = schema.get("paths", {})

    # 按路径排序保证幂等
    for path in sorted(paths.keys()):
        path_item = paths[path]
        for http_method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(http_method)
            if not op:
                continue
            entry = _entry_from_operation(path, http_method, op)
            name = str(entry.pop("_name"))
            if name in entries:
                # 冲突 → 追加序号（test: /api/sessions/{id} 与 /api/session/{id}）
                i = 1
                while f"{name}{i}" in entries:
                    i += 1
                name = f"{name}{i}"
            entries[name] = entry
    return entries


def render_ts(schema: dict[str, Any]) -> str:
    """schema → endpoints.ts 源码（含手工补录段标记）。"""
    entries = build_endpoint_entries(schema)
    lines: list[str] = [
        "// GENERATED FILE — DO NOT EDIT 生成段（由 scripts/gen_api.py 生成）",
        "// 手工补录段位于文件末尾，重新生成不会覆盖",
        "",
        "export interface ApiEndpoint {",
        "  /** 路径模板，如 /api/sessions/{session_id} */",
        "  path: string;",
        "  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';",
        "  /** 该端点是否需要请求体 */",
        "  needsBody: boolean;",
        "}",
        "",
        "export const ENDPOINTS = {",
    ]
    for name, entry in entries.items():
        lines.append(
            f"  {name}: {{ path: {json.dumps(str(entry['path']))}, "
            f"method: '{entry['method']}', needsBody: {str(entry['needsBody']).lower()} }},"
        )
    lines += [
        "} as const satisfies Record<string, ApiEndpoint>;",
        "",
        "// ═══════════════════════════════════════════════════════",
        "// 手工补录段（MANUAL）— 生成脚本不覆盖以下内容",
        "// 用途：schema 缺失但前端实际调用的端点（如 /api/session 单数别名）",
        "// 添加方式：直接在此处追加条目",
        "// ═══════════════════════════════════════════════════════",
        "export const MANUAL_ENDPOINTS = {",
        "  listSessionAlias: { path: '/api/session', method: 'GET', needsBody: false },",
        "  createSessionAlias: { path: '/api/session', method: 'POST', needsBody: true },",
        "  deleteSessionAlias: { path: '/api/session/{session_id}', method: 'DELETE', needsBody: false },",
        "  updateSessionAlias: { path: '/api/session/{session_id}', method: 'PATCH', needsBody: true },",
        "  exportSessionAlias: { path: '/api/session/{session_id}/export', method: 'POST', needsBody: false },",
        "  importSessionAlias: { path: '/api/session/import', method: 'POST', needsBody: true },",
        "  sessionMessagesAlias: { path: '/api/session/{session_id}/messages', method: 'GET', needsBody: false },",
        "} as const satisfies Record<string, ApiEndpoint>;",
        "",
    ]
    return "\n".join(lines)


def _load_schema(schema_path: str | None) -> dict[str, Any]:
    """从文件或 cscode.server.app 拉取 schema。"""
    if schema_path:
        raw: object = json.loads(Path(schema_path).read_text())
        assert isinstance(raw, dict)
        return raw
    from cscode.server.app import app  # type: ignore[import-untyped]

    schema: dict[str, Any] = app.openapi()
    return schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenAPI → TS 端点表生成器")
    parser.add_argument("--schema", help="OpenAPI schema JSON 文件（缺省从 cscode.server.app 生成）")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent.parent / "src/cscode/web/src/lib/api/generated/endpoints.ts"),
        help="输出 TS 文件路径",
    )
    args = parser.parse_args(argv)

    schema = _load_schema(args.schema)
    ts = render_ts(schema)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ts)
    print(f"Generated {len(build_endpoint_entries(schema))} endpoints → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
