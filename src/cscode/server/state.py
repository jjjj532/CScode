from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from cscode.core.coordinator import SessionCoordinator
from cscode.core.external_directory import ExternalDirectoryStore
from cscode.core.permission_v2 import SessionPermission
from cscode.core.plugin.host import PluginHost
from cscode.core.sharing import ShareStore
from cscode.core.tracker import TaskTracker
from cscode.core.workspace import WorkspaceStore
from cscode.lsp.manager import LSPManager
from cscode.server.audit_log import AuditLogStore, ErrorLogStore
from cscode.server.compactor import Compactor
from cscode.server.integration import IntegrationTokenStore, WebSocketManager
from cscode.server.projector import Projector
from cscode.server.question_registry import QuestionRegistry
from cscode.storage.db import Database
from cscode.storage.event_store import EventStore
from cscode.tools2.pty import PTYSessionManager


@dataclass
class AppState:
    db: Database | None = None
    event_store: EventStore | None = None
    coordinator: SessionCoordinator | None = None
    projector: Projector | None = None
    compactor: Compactor | None = None
    tracker: TaskTracker | None = None
    question_registry: QuestionRegistry | None = None
    tool_registry: Any = None
    workspace_store: WorkspaceStore | None = None
    share_store: ShareStore | None = None
    external_dir_store: ExternalDirectoryStore | None = None
    ws_manager: WebSocketManager | None = None
    token_store: IntegrationTokenStore | None = None
    pty_manager: PTYSessionManager | None = None
    lsp_manager: LSPManager | None = None
    audit_log: AuditLogStore | None = None
    error_log: ErrorLogStore | None = None
    active_agent_tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    session_queues: dict[str, asyncio.Queue[dict[str, object]]] = field(default_factory=dict)
    permission_store: dict[str, dict[str, object]] = field(default_factory=dict)
    permission_manager: SessionPermission | None = None
    plugin_host: PluginHost | None = None


state = AppState()
