"""Session input domain model types — pure data definitions.

These types model the "durable prompt admission" concept from SPEC §2.3:
prompts are admitted to a session input queue with a delivery mode
(steer or queue) and promoted to the LLM when the session is ready.

Types:
    DeliveryMode   — How an admitted input is promoted to the LLM.
    AdmittedInput  — A prompt admitted to the session input pipeline.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum


class DeliveryMode(StrEnum):
    """How an admitted input is promoted to the LLM.

    STEER — Promoted immediately within the current drain.
    QUEUE — Promoted only when the session drain is idle.
    """

    STEER = "steer"
    QUEUE = "queue"


@dataclass(frozen=True, slots=True)
class AdmittedInput:
    """A prompt admitted to the session's input pipeline.

    AdmittedInput records a prompt that has been accepted into the
    session's durable input queue but not yet promoted to the LLM.
    The ``promoted_seq`` field is set when the input is promoted.
    """

    id: str
    """Unique identifier for this admitted input."""

    session_id: str
    """The session this input belongs to."""

    prompt: str
    """The user prompt text."""

    delivery: DeliveryMode
    """How this input should be promoted (steer or queue)."""

    admitted_seq: int
    """Event sequence number at which this input was admitted."""

    time_created: datetime.datetime
    """Timestamp when this input was admitted."""

    promoted_seq: int | None = None
    """Event sequence number at which this input was promoted (None = not yet)."""
