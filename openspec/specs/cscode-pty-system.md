# P2-1: PTY 系统 — 伪终端交互会话

## 1. 问题

当前 `BashTool` 是无状态一次性执行：创建子进程 → 等待完成 → 返回输出。无法支持：

- 交互式 shell（cd、export、virtualenv activate 等状态保持）
- 长时运行命令的流式输出
- 在多个 LLM 工具调用间保持 shell 会话状态

## 2. 目标

提供一个有状态的 PTY (pseudoterminal) 工具，支持：

1. 创建持久化的 shell 会话（bash/zsh）
2. 向会话发送输入
3. 从会话读取输出（字节流）
4. 关闭/销毁会话
5. 同时管理多个独立会话
6. 会话超时自动清理

## 3. 接口定义

### 3.1 数据模型

```python
@dataclass
class PTYSession:
    """A persistent PTY session."""
    session_id: str          # 唯一标识
    shell: str               # /bin/bash /bin/zsh
    cwd: str                 # 当前工作目录
    created_at: float
    last_active: float
    process: asyncio.subprocess.Process
    master_fd: int           # PTY master fd
    reader_task: asyncio.Task | None  # 后台读取任务
    output_queue: asyncio.Queue[str]  # 输出缓冲区
    env: dict[str, str]      # 环境变量
```

### 3.2 Tool Input/Output Schemas

```python
class PTYCreateInput(BaseModel):
    shell: str = "/bin/bash"
    cwd: str | None = None        # 工作目录，默认当前
    env: dict[str, str] | None = None

class PTYCreateOutput(BaseModel):
    session_id: str
    shell: str
    cwd: str
    created_at: float

class PTYWriteInput(BaseModel):
    session_id: str
    data: str                      # 要发送到 PTY 的文本
    wait_for_prompt: bool = True   # 是否等待提示符出现后返回

class PTYWriteOutput(BaseModel):
    output: str                    # 命令执行后的输出
    exit_code: int | None = None    # 如果命令完成则返回

class PTYReadOutput(BaseModel):
    output: str                    # 缓冲区中的输出
    has_more: bool                 # 是否还有更多数据

class PTYCloseOutput(BaseModel):
    session_id: str
    closed: bool

class PTYListOutput(BaseModel):
    sessions: list[PTYCreateOutput]
```

### 3.3 Tool Class Structure

```python
class PTYTool(Tool[PTYInput, PTYOutput]):
    """Stateful PTY tool for interactive shell sessions."""
    name = "pty"
    description = "Manage persistent shell sessions via PTY"
    input_schema = PTYInput  # discriminated union
    output_schema = PTYOutput
```

由于 PTY 工具需要区分多个操作（create/write/read/close/list），输入模型使用 discriminated union：

```python
class PTYAction(str, Enum):
    CREATE = "create"
    EXEC = "exec"        # 写入 + 等待输出
    READ = "read"
    CLOSE = "close"
    LIST = "list"

class PTYInput(BaseModel):
    action: PTYAction
    # create params
    shell: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    # exec params
    session_id: str | None = None
    command: str | None = None
    timeout: int = 30000
    # read params
    # close params
```

### 3.4 行为定义

#### `action=create`
1. 分配 PTY (os.openpty)
2. 启动 shell 进程 (asyncio.create_subprocess_exec)
3. 启动后台读取任务将 PTY 输出存入 queue
4. 返回 session_id
5. 默认超时: 10 分钟无活动自动关闭

#### `action=exec`
1. 向指定 session 的 PTY 写入命令 + `\n`
2. 等待 shell 提示符出现（或超时）
3. 返回命令输出
4. 支持 `timeout` 参数

#### `action=read`
1. 从 session 的输出队列读取所有可用数据
2. 返回输出文本

#### `action=close`
1. 发送 `exit` 到 shell
2. 等待进程结束
3. 清理 PTY 文件描述符

#### `action=list`
1. 返回所有活跃 session 列表

## 4. 会话管理

```python
class PTYSessionManager:
    """Manages all active PTY sessions."""
    
    def __init__(self, max_sessions: int = 10, session_timeout: int = 600):
        self._sessions: dict[str, PTYSession] = {}
        self._max_sessions = max_sessions
        self._session_timeout = session_timeout
        self._cleanup_task: asyncio.Task | None = None
    
    async def create(self, ...) -> PTYSession: ...
    async def exec(self, session_id: str, command: str) -> PTYExecResult: ...
    async def read(self, session_id: str) -> str: ...
    async def close(self, session_id: str) -> bool: ...
    def list_sessions(self) -> list[PTYSession]: ...
    async def _cleanup_stale(self): ...  # 定期清理超时会话
```

## 5. 文件结构

```
src/cscode/tools2/
  pty.py           ← PTYTool + PTYSessionManager (新文件)
tests/
  test_pty.py      ← PTY 单元测试 (新文件)
src/cscode/app/
  factory.py       ← register PTYTool (修改)
```

## 6. 验收标准

1. [ ] `action=create` 创建 shell 会话，返回 session_id
2. [ ] `action=exec` 在会话中执行命令，保持状态（如 `cd` 后 `pwd` 正确）
3. [ ] `action=read` 读取输出缓冲区
4. [ ] `action=close` 关闭会话，清理资源
5. [ ] `action=list` 列出活跃会话
6. [ ] 多个独立会话互不干扰
7. [ ] 超时会话自动清理
8. [ ] 异常处理: 关闭已关闭的 session、超时、命令不存在
9. [ ] 注册到工具系统，在 factory.py 中生效

## 7. 依赖

- Python 标准库: `os`, `pty`, `select`, `termios`, `fcntl`, `signal`
- 无需外部依赖

## 8. 不做的

- 不实现 Web 终端/前端（P2-17 TUI 完整化时再做）
- 不实现全双工流（只用 request-response 模式）
- 不使用 `pyte`/`xterm.js` 等终端模拟库（只处理原始字节流）
