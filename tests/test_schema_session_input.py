"""Tests for Schema SessionInput types — DeliveryMode, AdmittedInput.

These types are pure dataclasses/enums in the schema layer.
They must have zero runtime dependencies on cscode.core or cscode.server.
"""

from __future__ import annotations

import datetime

from cscode.schema.session_input import AdmittedInput, DeliveryMode


class TestDeliveryMode:
    """DeliveryMode enum — how an admitted input is promoted."""

    def test_steer_value(self) -> None:
        assert DeliveryMode.STEER == "steer"

    def test_queue_value(self) -> None:
        assert DeliveryMode.QUEUE == "queue"

    def test_is_str_enum(self) -> None:
        assert issubclass(DeliveryMode, str)

    def test_all_members(self) -> None:
        assert set(DeliveryMode) == {DeliveryMode.STEER, DeliveryMode.QUEUE}


class TestAdmittedInput:
    """AdmittedInput — a prompt admitted to the session input queue."""

    def test_minimal_construction(self) -> None:
        """AdmittedInput requires only the required fields."""
        now = datetime.datetime.now(datetime.timezone.utc)
        inp = AdmittedInput(
            id="inp_abc123",
            session_id="sess_xyz",
            prompt="Hello, world!",
            delivery=DeliveryMode.STEER,
            admitted_seq=1,
            time_created=now,
        )
        assert inp.id == "inp_abc123"
        assert inp.session_id == "sess_xyz"
        assert inp.prompt == "Hello, world!"
        assert inp.delivery == DeliveryMode.STEER
        assert inp.admitted_seq == 1
        assert inp.time_created == now
        assert inp.promoted_seq is None

    def test_full_construction(self) -> None:
        """AdmittedInput accepts promoted_seq."""
        now = datetime.datetime.now(datetime.timezone.utc)
        inp = AdmittedInput(
            id="inp_def456",
            session_id="sess_uvw",
            prompt="List files",
            delivery=DeliveryMode.QUEUE,
            admitted_seq=5,
            time_created=now,
            promoted_seq=3,
        )
        assert inp.promoted_seq == 3

    def test_promoted_seq_is_optional(self) -> None:
        """promoted_seq defaults to None."""
        now = datetime.datetime.now(datetime.timezone.utc)
        inp = AdmittedInput(
            id="inp_ghi789",
            session_id="sess_rst",
            prompt="Read file",
            delivery=DeliveryMode.STEER,
            admitted_seq=10,
            time_created=now,
        )
        assert inp.promoted_seq is None

    def test_immutable(self) -> None:
        """AdmittedInput is frozen."""
        import dataclasses
        now = datetime.datetime.now(datetime.timezone.utc)
        inp = AdmittedInput(
            id="inp_imm",
            session_id="sess_imm",
            prompt="test",
            delivery=DeliveryMode.STEER,
            admitted_seq=1,
            time_created=now,
        )
        assert inp.__dataclass_params__.frozen  # type: ignore[attr-defined]

    def test_no_runtime_deps(self) -> None:
        """AdmittedInput does not import from cscode.core or cscode.server."""
        import inspect
        source = inspect.getsource(AdmittedInput)
        assert "cscode.core" not in source
        assert "cscode.server" not in source

    def test_delivery_enum_used(self) -> None:
        """AdmittedInput.delivery field is typed as DeliveryMode enum."""
        import typing
        now = datetime.datetime.now(datetime.timezone.utc)
        hints = typing.get_type_hints(AdmittedInput)
        assert hints["delivery"] is DeliveryMode
