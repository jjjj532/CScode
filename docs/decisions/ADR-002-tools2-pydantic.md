# ADR-002: Tool 系统 v2 使用 Pydantic v2 实现类型安全

**Status:** Accepted
**Date:** 2026-06-26

## Context

旧 `tools/` 的 `BaseTool` 使用 `parameters: dict` 和 `execute(args: dict)`：
```python
class BaseTool(ABC):
    parameters: dict[str, Any]   # JSON Schema dict
    async def execute(self, args: dict[str, Any]) -> ToolResult: ...
```

输入输出的类型安全全靠运行时检查。Tool 消费者（engine.py）需要手动 `json.loads()` 解析参数，
`ToolResult.data` 是 `str` 类型 — 丢失了结构化数据的类型信息。

OpenCode 使用 Effect Schema 做编译时 + 运行时双验证：
```typescript
Tool.make({
    input: Schema<Input>,    // 编译时类型 + 运行时 decode
    output: Schema<Output>,  // 编译时类型 + 运行时 encode
    execute: (input) => Effect<Output, ToolFailure>,
})
```

## Decision

`Tools2/` 使用 `Generic[InputT, OutputT : BaseModel]`：

```python
class Tool(ABC, Generic[InputT, OutputT]):
    input_schema: type[InputT]    # Pydantic BaseModel subclass
    output_schema: type[OutputT]  # Pydantic BaseModel subclass
    async def execute(self, input: InputT) -> ToolResult[OutputT]: ...
```

收益：
- 编译时: `execute()` 参数和返回值类型已知，mypy 可检查
- 运行时: `input_schema.model_validate(raw)` 校验输入
- JSON Schema 生成: `model_json_schema()` 自动给 LLM 使用

## Alternatives Considered

- **保持旧 dict 格式** — 无法获得类型检查收益。运行时崩溃是 CScode 最常见的 bug 来源。
- **dataclass + 手写 JSON Schema** — 需要维护两份定义，容易不一致。
- **msgspec** — 性能更好（尤其 JSON 编码），但生态不如 Pydantic（没有广泛验证过的 JSON Schema 输出）。
- **attrs + cattrs** — 功能类似 dataclass，JSON Schema 支持不如 Pydantic。

## Consequences

- ✅ 每个工具需要定义 Input/Output 两个 Pydantic model（代码量略增，但类型安全收益远大于成本）
- ✅ `model_json_schema()` 自动生成 LLM 需要的 JSON Schema
- ✅ `model_validate()` 提供运行时校验，定位问题更快
- ✅ 旧 `tools/` 代码不动，`tools2/` 是新实现（双轨并行）
- ⚠️ Pydantic v2 性能比 v1 好 5-10x，但仍比手写 dict 慢（对工具调用频率可忽略）
