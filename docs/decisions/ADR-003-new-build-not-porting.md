# ADR-003: 全新构建，非 1:1 翻译

**Status:** Accepted (Supersedes `docs/opencode-python-porting-plan.md`)
**Date:** 2026-06-26

## Context

最初计划是"1:1 还原 OpenCode 的 TypeScript 功能到 Python"。五维分析发现 OpenCode 的核心特性严重依赖 Effect.ts：
- **Effect Schema** — 编译时类型 + 运行时 decode + 自动 JSON Schema 生成
- **Effect Context** — 依赖注入 + 作用域管理（Layer/Service 模式）
- **Fiber** — 结构化并发工具执行
- **Effect State** — 可重放的状态管理

这些在 Python 中没有直接等价物，强行 1:1 翻译会导致代码风格怪异、性能差、难以维护。

## Decision

CScode 是**全新构建 + 接口驱动**的系统。核心原则：

1. **吸收架构思想，不复制实现** — 参考 OpenCode 的分层和接口模式
2. **用 Python 语言特性等效实现** — Pydantic v2 替代 Effect Schema，async/await 替代 Fiber
3. **独立编写所有代码** — 不引用 OpenCode 源码，所有注释用自己的话写
4. **接口参数名用 Python 风格** — 不做逐字对应（snake_case 代替 camelCase）

## What This Means

| 原来以为 | 实际做法 |
|----------|----------|
| 1:1 逐行翻译 TypeScript → Python | 理解架构后重新设计 Python 实现 |
| 复制 OpenCode 测试用例 | 用自己的测试数据和场景 |
| 保留 OpenCode 注释 | 所有注释重新撰写 |
| 复制包结构 | 按 Python 惯例组织代码 |

## Consequences

- ✅ 代码库无知识产权风险（非派生作品）
- ✅ 代码风格自然 Pythonic，无 TypeScript 痕迹
- ✅ 实现可以自由选择最佳 Python 库
- ⚠️ 需要消化和理解 OpenCode 架构，不能直接"翻译"
- ⚠️ 开发速度可能比"翻译"慢，但最终质量更高
