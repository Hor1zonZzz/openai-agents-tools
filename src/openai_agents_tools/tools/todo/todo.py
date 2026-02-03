"""
set_todo_list - Update the todo list for task tracking.

This tool helps track progress on multi-step tasks by maintaining
a structured todo list.
"""

from __future__ import annotations

from typing import Literal

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_success


class TodoItem(BaseModel):
    """A single todo item."""

    title: str = Field(description="The title of the todo", min_length=1)
    status: Literal["pending", "in_progress", "done"] = Field(
        description="The status of the todo"
    )


class SetTodoListParams(BaseModel):
    """Parameters for set_todo_list tool."""

    todos: list[TodoItem] = Field(description="The updated todo list")


@function_tool
async def set_todo_list(
    ctx: RunContextWrapper[KimiToolContext], params: SetTodoListParams
) -> str:
    """
    Update the whole todo list.

    Todo list is a simple yet powerful tool to help you get things done. You
    typically want to use this tool when the given task involves multiple
    subtasks/milestones, or multiple tasks are given in a single request.

    This is the only todo list tool available. Each time you want to operate
    on the todo list, you need to update the whole list. Make sure to maintain
    the todo items and their statuses properly.

    Once you finish a subtask/milestone, remember to update the todo list to
    reflect the progress.

    When NOT to use this tool:
    - When the user just asks a simple question
    - When the task takes only a few steps to complete
    - When the user prompt is very specific and straightforward

    Be flexible - you may start using todo list and realize the task is simple,
    or you may realize a task is complex after starting and then use todo list.
    """
    # Format the todo list as a readable string
    if not params.todos:
        return format_success("", "Todo list cleared")

    lines = ["Todo list updated:"]
    for todo in params.todos:
        status_icon = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "done": "[x]",
        }[todo.status]
        lines.append(f"  {status_icon} {todo.title}")

    return format_success("\n".join(lines), "Todo list updated")
