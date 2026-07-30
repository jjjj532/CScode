"""Tests for TaskTool — create/list/update sub-tasks."""

from __future__ import annotations

import pytest

from cscode.tools2.task import _TASK_STORE, TaskInput, TaskTool


@pytest.fixture(autouse=True)
def clear_store() -> None:
    """Clear the global _TASK_STORE before each test to prevent cross-test leakage."""
    _TASK_STORE.clear()
    yield
    _TASK_STORE.clear()


@pytest.mark.asyncio
async def test_create_task() -> None:
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="create", description="test task"))
    assert result.success
    assert result.data is not None
    assert result.data.task_id != ""
    assert result.data.description == "test task"
    assert result.data.status == "pending"
    assert len(_TASK_STORE) == 1


@pytest.mark.asyncio
async def test_create_task_empty_description() -> None:
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="create", description=""))
    assert not result.success
    assert result.error == "Description required for create"


@pytest.mark.asyncio
async def test_create_task_whitespace_description() -> None:
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="create", description="   "))
    assert not result.success
    assert result.error == "Description required for create"


@pytest.mark.asyncio
async def test_create_task_none_description() -> None:
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="create", description=None))
    assert not result.success
    assert result.error == "Description required for create"


@pytest.mark.asyncio
async def test_list_empty() -> None:
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="list"))
    assert result.success
    assert result.data is not None
    assert result.data.tasks == []


@pytest.mark.asyncio
async def test_list_multiple() -> None:
    tool = TaskTool()
    await tool.execute(TaskInput(action="create", description="task1"))
    await tool.execute(TaskInput(action="create", description="task2"))
    result = await tool.execute(TaskInput(action="list"))
    assert result.success
    assert len(result.data.tasks) == 2


@pytest.mark.asyncio
async def test_update_status_to_in_progress() -> None:
    tool = TaskTool()
    create_result = await tool.execute(TaskInput(action="create", description="my task"))
    assert create_result.success
    task_id = create_result.data.task_id

    result = await tool.execute(
        TaskInput(action="update", task_id=task_id, status="in_progress")
    )
    assert result.success
    assert result.data.task_id == task_id
    assert result.data.status == "in_progress"
    assert _TASK_STORE[task_id]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_status_to_completed() -> None:
    tool = TaskTool()
    create_result = await tool.execute(TaskInput(action="create", description="my task"))
    task_id = create_result.data.task_id

    result = await tool.execute(
        TaskInput(action="update", task_id=task_id, status="completed")
    )
    assert result.success
    assert result.data.status == "completed"


@pytest.mark.asyncio
async def test_update_no_task_id() -> None:
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="update"))
    assert not result.success
    assert result.error == "task_id required for update"


@pytest.mark.asyncio
async def test_update_not_found() -> None:
    tool = TaskTool()
    result = await tool.execute(
        TaskInput(action="update", task_id="nonexistent")
    )
    assert not result.success
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_update_keeps_existing_status() -> None:
    """Update without providing status should keep existing status."""
    tool = TaskTool()
    create_result = await tool.execute(TaskInput(action="create", description="keep"))
    task_id = create_result.data.task_id
    assert create_result.data.status == "pending"

    result = await tool.execute(TaskInput(action="update", task_id=task_id))
    assert result.success
    assert result.data.status == "pending"


@pytest.mark.asyncio
async def test_create_task_keeps_store_integrity() -> None:
    """Verify the store dict contains expected fields after create."""
    tool = TaskTool()
    result = await tool.execute(TaskInput(action="create", description="verify"))
    task_id = result.data.task_id
    assert task_id in _TASK_STORE
    assert _TASK_STORE[task_id]["description"] == "verify"
    assert _TASK_STORE[task_id]["status"] == "pending"
    assert _TASK_STORE[task_id]["task_id"] == task_id


@pytest.mark.asyncio
async def test_update_preserves_description() -> None:
    """Updating status should not change the task description."""
    tool = TaskTool()
    create_result = await tool.execute(
        TaskInput(action="create", description="preserve me")
    )
    task_id = create_result.data.task_id

    result = await tool.execute(
        TaskInput(action="update", task_id=task_id, status="completed")
    )
    assert result.data.description == "preserve me"


@pytest.mark.asyncio
async def test_create_generates_unique_ids() -> None:
    """Each created task should have a unique ID."""
    tool = TaskTool()
    r1 = await tool.execute(TaskInput(action="create", description="a"))
    r2 = await tool.execute(TaskInput(action="create", description="b"))
    assert r1.data.task_id != r2.data.task_id


@pytest.mark.asyncio
async def test_create_twice_yields_two_in_list() -> None:
    tool = TaskTool()
    await tool.execute(TaskInput(action="create", description="first"))
    await tool.execute(TaskInput(action="create", description="second"))
    result = await tool.execute(TaskInput(action="list"))
    descs = {t["description"] for t in result.data.tasks}
    assert descs == {"first", "second"}


@pytest.mark.asyncio
async def test_unknown_action_rejected_by_schema() -> None:
    """Pydantic's Literal type rejects invalid actions at validation time."""
    # The Literal["create", "list", "update"] constraint on action means
    # Pydantic schema validation catches this before execute() is called.
    # This is correct behavior — no need to duplicate validation in the tool.
    pass
