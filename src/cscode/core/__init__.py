"""CScode Core Layer — sessions, coordinator, runner.

  SessionV2           — Event Sourcing-based session
  SessionProjector    — Events → SessionState reconstruction
  SessionCoordinator  — Per-session state machine (run/wake/interrupt)
  SessionRunner       — Standardized agent loop using LLM layer
  Config              — config.py: flat configuration
  TuiSessionManager  — tui_sessions.py: TUI session management
  InputInbox          — session_input.py: event-sourced input queue
  Attachment          — attachment.py: file attachment model
  Credential          — credential.py: secure credential storage
  Catalog             — catalog.py: model/provider/agent registry
  BackgroundJobQueue  — background_job.py: async background job queue
  I18n                — i18n.py: internationalization
"""

from __future__ import annotations

from cscode.core.agent import AgentMode, AgentTab, TabManager
from cscode.core.attachment import Attachment
from cscode.core.background_job import BackgroundJobQueue, JobStatus, JobStore
from cscode.core.catalog import AgentEntry, Catalog, ModelEntry, ProviderEntry
from cscode.core.coordinator import SessionCoordinator
from cscode.core.credential import Credential, CredentialStore
from cscode.core.i18n import I18n
from cscode.core.i18n import t as i18n_t
from cscode.core.runner import SessionRunner
from cscode.core.session import SessionProjector, SessionV2
from cscode.core.session_input import InputInbox, InputInboxState, QueuedInput
from cscode.core.tui_sessions import TuiMessage, TuiSession, TuiSessionManager

# Backward compatibility shims for legacy tests
# Map old names to new classes
Session = TuiSession
SessionManager = TuiSessionManager

# Create a simple status enum for compatibility
class SessionStatus:
    ACTIVE = "active"
    IDLE = "idle"
    COMPLETED = "completed"

__all__ = [
    "SessionV2",
    "SessionProjector",
    "SessionCoordinator",
    "SessionRunner",
    "InputInbox",
    "InputInboxState",
    "QueuedInput",
    "Attachment",
    "Credential",
    "CredentialStore",
    "Catalog",
    "ModelEntry",
    "ProviderEntry",
    "AgentEntry",
    "BackgroundJobQueue",
    "JobStatus",
    "JobStore",
    "I18n",
]
