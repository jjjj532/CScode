# Fix v8 Report Issues

## P0-8: getThemeColors TypeError
**结论**: 误报。`getThemeColors`/`exportedColors` 不存在于源码或 node_modules 任何文件中。
来源：TRAE 浏览器插件注入。无需修复。

## P1-5: text.delta 数据库膨胀
**问题**: 每个字符增量独立持久化，一次对话产生 300+ 事件。
**分析**: 
- P0-3 原修复将 `text.delta` 加入 `PERSIST_EVENT_TYPES`
- 但 `text.ended` 已在列表中，包含完整消息内容
- 并发 session 丢失事件的根因是 P0-6（abort）和 P0-7（事件丢弃），已修复
- `text.delta` 持久化对会话历史回放无意义（只显示最终 `text.ended`）

**修复**: 从 `PERSIST_EVENT_TYPES` 移除 `text.delta`。

## P1-6: Settings 权限加载慢
**分析**: 权限规则查询需优化。低优先级。

## P2-2: 构建 chunk 1.3MB
**分析**: 需 code splitting。低优先级，暂不处理。
