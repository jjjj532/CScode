# ADR-001: 三层架构 (Schema → LLM → Core → App)

**Status:** Accepted
**Date:** 2026-06-26

## Context

OpenCode 使用 Effect.ts 做依赖注入，packages 之间有清晰的单向依赖链（schema → llm → core → opencode → protocol）。
CScode 初始版本没有架构分层，类型定义散落在各个模块中，`engine.py` 单文件 474 行承载了所有循环逻辑、权限检查、事件发布、工具执行的职责。

关键问题：
- 没有统一的数据模型层 → 模块之前用 dict 通信，类型安全靠运行时
- Provider 调用直接嵌入在 engine 中 → 无法独立测试
- 没有纯核心层 → CLI/TUI/Server 代码耦合了业务逻辑

## Decision

采用严格的四模块单向依赖架构：

```
schema (零依赖) → llm → core → app
```

每层只依赖正下层，禁止跨层 import。用 Python 的 `import` 机制做编译时检查。

| Layer | Import Rule | Examples |
|-------|------------|----------|
| `schema/` | 零依赖 | dataclass、enum、typing、pydantic |
| `llm/` | 仅 `schema/` | `schema.Message`, `schema.LLMError` |
| `core/` | `schema/` + `llm/` | `llm.LLMService`, `schema.ToolChoice` |
| `app/` | `core/` + `llm/` + `schema/` | `core.SessionRunner` |

## Alternatives Considered

- **直接重构旧代码** — 风险高，无法渐进切换。一旦开始改 engine.py，旧功能全部不可用。
- **使用 DI 框架** — Python 没有 Effect.ts 级别的类型安全 DI。`inject`、`dependency-injector` 都达不到编译时安全检查。
- **复制 OpenCode 的包结构** — TypeScript 的 package 组织方式（monorepo + 20+ packages）在 Python 单包中不需要也不适合。

## Consequences

- ✅ 模块可以独立测试，不依赖 app 层的 UI 代码
- ✅ 每层的公共接口通过 `__init__.py` 显式导出，隐藏实现细节
- ✅ 新代码可以通过适配器调用旧代码，实现渐进迁移
- ⚠️ 禁止跨层 import 约束需要在 CI 和 code review 中落实
- ⚠️ 需要定期用 grep 检查违规: `grep -r "from cscode.core" src/cscode/llm/`
