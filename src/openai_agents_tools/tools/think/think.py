"""
think - A tool for complex reasoning and working memory.

This tool allows the model to explicitly log thoughts without
changing any state or obtaining new information.
"""

from __future__ import annotations

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_success


class ThinkParams(BaseModel):
    """Parameters for think tool."""

    thought: str = Field(description="A thought to think about.")


@function_tool
async def think(
    ctx: RunContextWrapper[KimiToolContext], params: ThinkParams
) -> str:
    """
    Use this tool to think about something.

    It will not obtain new information or change any state, but just append
    the thought to the log. Use it when complex reasoning or some cache
    memory is needed.

    This is useful for:
    - Breaking down complex problems step by step
    - Recording intermediate reasoning
    - Keeping track of important observations
    - Planning next steps before acting
    """
    # The thought is logged in the conversation history
    # We just acknowledge it was recorded
    return format_success("", "Thought logged")
