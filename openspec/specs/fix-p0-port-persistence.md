# Fix P0 Issues: Vite Port & Event Persistence

## P0-1: Vite Proxy Default Port

**问题**: `vite.config.ts` 中 proxy target 默认端口为 8080，后端实际运行在 8000。

**修复**: 将默认值从 `8080` 改为 `8000`。

**验证**: `vite.config.ts` 中 `proxyTarget` 默认值应为 `http://localhost:8000`，环境变量 `CSCORE_SERVER_PORT` 仍可覆盖。

## P0-3: Event Persistence Missing text.delta

**问题**: `PERSIST_EVENT_TYPES` 缺少 `text.delta`，导致流式内容不落库。

**影响**: 并发 session 的消息内容完全丢失，只有 `step.started` 被持久化。

**修复**: 将 `"text.delta"` 添加到 `PERSIST_EVENT_TYPES`。

**验证**: 
1. 单元测试：验证 `PERSIST_EVENT_TYPES` 包含 `text.delta`
2. Stream 测试：模拟 `TextDelta` 事件，验证被持久化

## P0-2: getThemeColors TypeError (False Positive)

**结论**: `getThemeColors` 和 `exportedColors` 不存在于源码或 node_modules 中。该错误是测试环境误报，无需修复。
