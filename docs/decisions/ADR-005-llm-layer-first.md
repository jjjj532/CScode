# ADR-005: LLM 层优先，Event Sourcing 延期

**Status:** Accepted
**Date:** 2026-06-26

## Context

五维分析识别出 OpenCode 相比 CScode 的 4 个 P0 差距：

1. Tool.definition + Tool.make 分离（类型安全）
2. **LLM.generate 自动 tool 循环**（自动工具编排）
3. 精确权限规则匹配（安全模型）
4. Session 恢复机制（Event Sourcing）

其中 tools2 已经完成（解决差距 #1）。开发资源有限，需要决定下一个模块的优先级。

Options:
- A) LLM 层优先 → 先把 tools2 集成到模型调用流程中，让核心循环跑通
- B) Event Sourcing 优先 → 先重写 session 存储
- C) 权限系统优先 → 先对齐安全模型

## Decision

**Option A: LLM 层优先。**

依据：
1. **依赖顺序:** LLM 层介于 schema 和 core 之间，必须先完成 LLM 才能重构 core。Event Sourcing 是 core 层的事。
2. **最大杠杆:** tools2 已经有类型安全的工具，但没有 LLM 调用它们。LLM 层让工具循环跑通，之后所有功能都可以串联。
3. **最小风险:** LLM 层通过适配器调用旧 provider，不会影响现有的 provider 调用路径。

```
当前状态:   schema → tools2  (各自独立)
添加 LLM:  schema → tools2 + LLM  (工具可被 LLM 调用)
下个迭代:  schema → llm → core  (完整的三层架构)
```

## Consequences

- ✅ LLM 层完成后，tools2 第一次被实际集成到模型调用流程中
- ✅ Event Sourcing 表结构已存在（migration_003），延期只是不使用，不阻塞
- ✅ 按依赖顺序推进，不跳步
- ⚠️ SessionManager 继续使用内存 dict + SQLite 直接读写，EventStore 闲置
- ⚠️ 权限系统仍然使用粗粒度的 allow/deny，缺少 wildcard 匹配
- ⚠️ 这两个 P0 项目会积累"技术债"，在 Core 层迭代中集中解决
