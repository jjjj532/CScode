"""CScode Core Layer — Event Sourcing engine, session management, agent loop.

New architecture (Phase 2+):
  SessionV2           — Event Sourcing-based session
  SessionProjector    — Events → SessionState reconstruction
  SessionCoordinator  — Per-session state machine (run/wake/interrupt)
  SessionRunner       — Standardized agent loop using LLM layer

Legacy (existing, stable):
  Agent               — engine.py: traditional agent loop
  Config              — config.py: flat configuration
  PermissionService   — permissions.py: tool permission checks
  TuiSessionManager  — tui_sessions.py: TUI session management
  EventBus            — events.py: pub/sub event system
"""

from __future__ import annotations

from cscode.core.coordinator import SessionCoordinator
from cscode.core.runner import SessionRunner
from cscode.core.session import SessionProjector, SessionV2
from cscode.core.tui_sessions import TuiSession, TuiSessionManager

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
]
