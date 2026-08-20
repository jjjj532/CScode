"""ToolResult 判别联合 — G-3 (spec §4.3)。

对齐 OpenCode §2.5 ToolResultValue：工具执行结果可以是 JSON、文本、
错误或内容块列表，调用方按 ``kind`` 判别处理。

对比 OpenCode packages/tool/src/result.ts：
  - ToolResultValue  = { kind: 'json'|'text'|'error'|'content', ... }
  - ToolOutput       = { structured?, content? }
本实现用 Python dataclass 表达同一形状。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from cscode.schema.messages import (
    MediaPart,
    Part,
    ReasoningPart,
    SystemPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


@dataclass(frozen=True, slots=True)
class ToolResultValue:
    """判别联合：工具执行结果的四种形态（OpenCode ToolResultValue）。"""

    kind: Literal["json", "text", "error", "content"]
    json: Any | None = None
    text: str | None = None
    error: str | None = None
    content: list[Part] | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为判别联合形状（测试锁定 JSON 形状）。"""
        result: dict[str, Any] = {"kind": self.kind}
        match self.kind:
            case "json":
                result["json"] = self.json
            case "text":
                result["text"] = self.text
            case "error":
                result["error"] = self.error
            case "content":
                result["content"] = [_part_to_dict(p) for p in (self.content or [])]
        return result

    @classmethod
    def from_json(cls, value: Any) -> ToolResultValue:
        return cls(kind="json", json=value)

    @classmethod
    def from_text(cls, text: str) -> ToolResultValue:
        return cls(kind="text", text=text)

    @classmethod
    def from_error(cls, error: str) -> ToolResultValue:
        return cls(kind="error", error=error)


def _part_to_dict(part: Part) -> dict[str, Any]:
    """Serialize a single Part to the wire shape (mirrors Message.to_dict).

    Kept local to schema.tool_result so ToolResultValue can serialize
    content blocks without pulling in Message itself (avoids import cycle).
    """
    match part:
        case SystemPart(text=t) | TextPart(text=t):
            return {"type": "text", "text": t}
        case MediaPart(media_type=m, data=d):
            return {"type": "media", "media_type": m, "data": d}
        case ToolCallPart(tool_call_id=i, name=n, args=a):
            return {"type": "tool-call", "tool_call_id": i, "name": n, "args": a}
        case ToolResultPart(tool_call_id=i, name=n, result=r, is_error=e):
            return {"type": "tool-result", "tool_call_id": i, "name": n, "result": r, "is_error": e}
        case ReasoningPart(text=t, signature=s):
            entry: dict[str, Any] = {"type": "reasoning", "text": t}
            if s is not None:
                entry["signature"] = s
            return entry
    raise TypeError(f"Unsupported part type: {type(part)!r}")


@dataclass(frozen=True, slots=True)
class ToolOutput:
    """工具执行的结构化输出（OpenCode ToolOutput）。

    ``structured`` 是机器可读的结构化数据；``content`` 是面向模型的内容块。
    两者均可选，至少一个非空。
    """

    structured: dict[str, Any] | None = None
    content: list[Part] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> ToolOutput:
        return cls(content=[TextPart(text=text)])

    @classmethod
    def from_structured(cls, data: dict[str, Any]) -> ToolOutput:
        return cls(structured=data)
