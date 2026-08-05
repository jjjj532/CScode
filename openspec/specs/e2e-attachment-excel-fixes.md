# Spec: E2E 附件生成 Excel 场景 6 项问题修复 (v0.3.5)

## Objective
修复 `INVESTIGATION_REPORT_v035_attachment_excel.md` 发现的 6 个问题（2 阻断 + 4 非阻断），覆盖前后端。

## 已核实现状（对照当前代码）

| # | 问题 | 严重度 | 核实结果 |
|---|------|--------|---------|
| 1 | Excel 文件在 /tmp 用户不可见 | 中/阻断(UX) | 后端已有 `OUTPUTS_DIR=/tmp/cscode-outputs` + `file_created` SSE 事件（app.py L944）；Tauri 已有 `open_output_file` 命令（lib.rs L287，Finder reveal）。**前端 `case 'file_created': break;` 完全忽略该事件** ← 核心缺口。报告文件在 `/tmp/*.xlsx`（非 OUTPUTS_DIR），需扩展检测 |
| 2 | 响应内容重复输出 | 高/阻断 | useChat.ts 已有 session_id 事件过滤（L152）+ controller 身份比对（L225）+ abort 守卫。竞态窗口缩小但未消除：`abortSession` 主动 abort 后 4 秒内快速重发仍可能双流 |
| 3 | 4 条空 assistant 消息 | 中 | useSessionStore.ts `step.started` 直接创建空 assistant 占位（L211-224，绕过 appendMessage 的空消息丢弃保护）；`text.ended` 空内容 `return s`。后端 projector 对 `step.started` 也可能投影 |
| 4 | tool.success/failed 未持久化 | 中 | `PERSIST_EVENT_TYPES` 已含两者（L89-99）+ `_llm_event_to_dict` 已映射 ToolResult→tool.success（L137-165）+ `on_event` 已持久化（L757-773）。**实现已就位，可能为旧构建**。需实测 + 补回归测试 |
| 5 | 案例生成耗时 8 分钟 | 中/性能 | write 工具 `Path(input.path)` 直接相对路径写（tools2/write.py L30），相对路径落到进程 CWD，LLM 用相对路径失败重试；heredoc 中文需验证 |
| 6 | run_state 返回 idle 但实际执行 | 中 | `_handle_chat_stream` 未调用 mark_run_start/complete（已确认无引用）；`/stop` 端点（routes/sessions.py L131）取消任务但不标记 run_state。`SessionExecution` 类存在但未用于 chat_stream |

## 验收标准

### P1: 问题 1 — 打开生成文件的入口
- [x] 前端消费 `file_created` SSE 事件：创建 `SessionFilesPanel.tsx`，在 assistant 消息下方渲染「📄 文件名 — 在 Finder 中显示」按钮（useChat.ts `case 'file_created'` 消费 → `addSessionFile`）
- [x] 点击按钮调用 Tauri `open_output_file(filename)`（web 环境降级：复制完整路径 + toast）
- [x] 后端 `file_created` 检测扩展：`_collect_new_artifacts()` 扫描 OUTPUTS_DIR 全部文件 + /tmp 顶层扩展名白名单（xlsx/xls/docx/doc/pdf/csv/zip/pptx/png/jpg/jpeg），mtime 过滤，去重
- [x] Tauri `open_output_file` 支持绝对路径（后端发完整路径）
- [x] 回归测试：useChat file_created 事件被消费（useChat.test.tsx）；后端检测含 /tmp 文件（test_artifact_detection.py 4 passed）；store addSessionFile/clearSessionFiles（stores.test.ts）

### P2: 问题 2 — 响应重复
- [x] 发送冷却：`SEND_COOLDOWN_MS=1000`，stream 结束后 1s 冷却期内禁止同一 session 再次发送（toast「发送太快」），杜绝双流（useChat.ts `lastSendAt`）
- [x] 回归测试：快速连点同 session，第二次被冷却拦截，只发 1 个请求（useChat.test.tsx `blocks a duplicate send`）

### P3: 问题 3 — 空 assistant 消息
- [x] `step.started` 不再创建空 assistant 占位（useSessionStore.ts 仅重置 thinking + toolCalls）
- [x] `text.delta` 惰性创建 assistant 消息（已存在逻辑，占位删除后自然生效）
- [x] 后端 projector 对 `step.started` 不投影空 assistant 消息（test_projector.py `test_step_events_do_not_create_empty_assistant_messages`）
- [x] 回归测试：stores.test.ts 3 个 applyEvent 行为测试（step.started 不建占位 / text.delta 惰性创建 / delta 后 step.started 保留消息）

### P4: 问题 4 — tool 事件持久化实测
- [x] 回归测试锁定行为：`_llm_event_to_dict` 映射 ToolResult→tool.success、ToolFailure→tool.failed；PERSIST_EVENT_TYPES 含两者；事件持久化到 EventStore（test_tool_event_persistence.py 4 passed）
- [x] 结论：实现已就位，补回归测试锁行为（符合 spec 约束「若实测已工作，仅补回归测试」）

### P5: 问题 5 — 工具路径与性能
- [x] write 工具支持相对路径：`WriteInput.cwd`，相对路径基于 cwd 或 `Path.cwd()` 解析，`expanduser` + `resolve()`（tools2/write.py）
- [x] LLM 系统提示规则 8：引导产物写入 `OUTPUTS_DIR` 用绝对路径，禁止裸相对路径（app.py `_build_system_prompt`）
- [x] 回归测试：write 相对路径/cwd/~/绝对路径（test_tools2_impl.py 6 passed）；系统提示含「/tmp/cscode-outputs / absolute paths / never bare relative paths」（test_server_globals.py 2 passed）

### P6: 问题 6 — run_state 状态机
- [x] `_handle_chat_stream`：agent_task 启动前 `mark_run_start`；成功 `mark_run_complete`；异常 `mark_run_error`；客户端断开/取消 `mark_run_stop`
- [x] `/stop` 端点：取消任务后 `mark_run_stop`（加载 SessionV2，`seq > 0` 才标记）
- [x] 回归测试：停端点标记 run_state=stopped（test_session_run_state.py `TestStopEndpointRunState`）

## 验证证据（V0.3.5）
- 后端新增测试：44 passed（artifact 4 + tool persistence 4 + projector 5 + run_state 13 + tools2 6 + server_globals 2 + 既有项）
- 后端全量 pytest：2500 passed / 2 failed / 4 skipped（2 failed 均为 `test_worktree.py` 中文 git 输出「致命错误」与英文正则不匹配，预存环境问题，非本次改动引起）
- 前端 jest：181 passed（22 suites）
- 前端 tsc --noEmit：无错；vite build：成功
- mypy / ruff：本次改动的 5 个后端文件全部通过（全屏 27+1 个错误均在未改文件，预存）

## 技术栈
- Python: FastAPI, pytest + pytest-asyncio
- React 18 + TS + Zustand + Jest 29 + React Testing Library
- Tauri v2 (Rust) — `open_output_file` 已有，仅前端接线

## 约束
- TDD：先写失败测试再实现
- 不动 `providers/`、`sdk/` 非活动路径
- 问题 4 若实测已工作，仅补回归测试锁行为
