# Session V2 Input/Runner System
# Task 1.3: P0.3 - Session V2 Input/Runner 基础
# Based on SPEC.md 2.3.x

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable


# === SPEC 2.3.1: DeliveryMode ===
class DeliveryMode(Enum):
    """How input should be delivered to the session"""
    STEER = "steer"   # Immediate, interrupts queue
    QUEUE = "queue"   # Queued, processed in order

# === SPEC 2.3.2: AdmittedInput ===
@dataclass
class AdmittedInput:
    """An input that has been admitted to the session"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "user"
    content: str = ""
    mode: DeliveryMode = DeliveryMode.QUEUE
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_steer(self) -> bool:
        return self.mode == DeliveryMode.STEER

    @property
    def is_queued(self) -> bool:
        return self.mode == DeliveryMode.QUEUE

# === SPEC 2.3.3: SessionInput API ===
class SessionInput:
    """Manages admitted inputs for a session"""

    def __init__(self):
        self._steers: list[AdmittedInput] = []
        self._queue: list[AdmittedInput] = []
        self._lock = asyncio.Lock()

    async def admit(
        self,
        content: str,
        role: str = "user",
        mode: DeliveryMode = DeliveryMode.QUEUE,
        metadata: dict[str, Any] | None = None,
    ) -> AdmittedInput:
        """Admit a new input to the session"""
        async with self._lock:
            inp = AdmittedInput(
                content=content,
                role=role,
                mode=mode,
                metadata=metadata or {},
            )

            if mode == DeliveryMode.STEER:
                self._steers.append(inp)
            else:
                self._queue.append(inp)

            return inp

    async def promote_steers(self) -> list[AdmittedInput]:
        """Promote all steer inputs for processing"""
        async with self._lock:
            steers = self._steers.copy()
            self._steers.clear()
            return steers

    async def promote_next_queued(self) -> AdmittedInput | None:
        """Promote the next queued input"""
        async with self._lock:
            if self._queue:
                return self._queue.pop(0)
            return None

    def has_pending(self) -> bool:
        """Check if there are pending inputs"""
        return len(self._steers) > 0 or len(self._queue) > 0

    def pending_count(self) -> int:
        """Count of pending inputs"""
        return len(self._steers) + len(self._queue)

    def peek_steers(self) -> list[AdmittedInput]:
        """Peek at steers without removing"""
        return self._steers.copy()

    def peek_queue(self, n: int = 5) -> list[AdmittedInput]:
        """Peek at queued inputs"""
        return self._queue[:n]

# === SPEC 2.3.4: SessionRunner ===
Response = dict[str, Any]
Handler = Callable[[], Awaitable[Response]]

class SessionRunner:
    """Runs a session, processing inputs"""

    def __init__(self, session_input: SessionInput):
        self.session_input = session_input
        self._running = False
        self._handlers: list[Handler] = []

    def register_handler(self, handler: Handler) -> None:
        """Register a handler to process inputs"""
        self._handlers.append(handler)

    async def run(self) -> None:
        """Main run loop"""
        self._running = True

        while self._running:
            # Process steers first
            steers = await self.session_input.promote_steers()
            for steer in steers:
                await self._process_input(steer)

            # Then process queued
            next_queued = await self.session_input.promote_next_queued()
            if next_queued:
                await self._process_input(next_queued)

            if self._running and not self.session_input.has_pending():
                await asyncio.sleep(0.1)

    async def _process_input(self, inp: AdmittedInput) -> None:
        """Process a single input"""
        for handler in self._handlers:
            try:
                await handler()
            except Exception as e:
                print(f"Handler error: {e}")

    async def stop(self) -> None:
        """Stop the run loop"""
        self._running = False

def create_session_input() -> SessionInput:
    """Create a new SessionInput instance"""
    return SessionInput()
