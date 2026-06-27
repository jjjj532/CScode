# ADR-004: 旧代码不动，适配器过渡

**Status:** Accepted
**Date:** 2026-06-26

## Context

系统重构中最大的风险是改旧代码引入 regression。CScode 是正在使用的项目，
`tools/`、`providers/`、`engine.py`、`session_manager.py` 中的代码已经在生产环境运行。
直接修改这些文件的风险：

- 新代码的 bug 会影响旧功能
- 重构途中需要修 bug 时，很难区分是重构导致的还是原有的
- 无法渐进上线（all or nothing）

## Decision

**所有旧代码一行不改。** 新代码（`tools2/`、`llm/`、`core/`）通过适配器模式调用旧实现：

```python
# src/cscode/llm/adapters/legacy.py
class LegacyProviderAdapter:
    """Adapter: 新 LLMService 接口 → 旧 LLMProvider 实现。"""
    def __init__(self, old_provider: LLMProvider):
        self._old = old_provider

    async def generate(self, request: LLMRequest) -> LLMResponse:
        # 转换 request → 旧格式
        old_messages = self._convert_messages(request.messages)
        result = await self._old.complete(old_messages, ...)
        # 转换旧格式 → response
        return self._convert_result(result)
```

Feature flag 控制使用新旧路径：

```python
# config.py
class FeatureFlag:
    use_new_session = False  # 🔒 默认使用旧系统
    use_new_llm = False
```

## Consequences

- ✅ 任何阶段都可以回退到旧系统（仅需关闭 feature flag）
- ✅ 重构不阻塞业务功能开发
- ✅ 新旧系统可以 A/B 测试
- ⚠️ 代码库短期内双轨并行，文件数量和 import 路径增加
- ⚠️ 需要维护适配器的正确性（适配器本身的 bug 会影响判断）
