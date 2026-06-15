# Spec: TUI Session Support

## Objective

在 TUI (Textual) 界面中集成 SessionManager，支持会话管理命令。

## Success Criteria
- [ ] TUI 内支持 `/sessions` 命令列出会话
- [ ] TUI 内支持 `/new` 命令创建新会话
- [ ] TUI 内支持 `/switch <id>` 命令切换会话
- [ ] TUI 内支持 `/kill <id>` 命令终止会话
- [ ] TUI 启动时自动创建/恢复会话

## Tech Stack
- Python
- Textual (已有)
- SessionManager (已实现)

## Commands

在 TUI 输入框中输入：
```
/sessions  或 /s   # 列出所有会话
/new       或 /n   # 创建新会话
/switch <id>       # 切换到指定会话
/kill <id>         # 终止指定会话
```
