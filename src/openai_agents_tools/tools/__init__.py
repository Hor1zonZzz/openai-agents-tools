"""
All tools for OpenAI Agents SDK.

This module provides easy access to all tools and tool categories.
"""

from typing import Any

from .file import (
    glob_tool,
    grep,
    read_file,
    read_media_file,
    str_replace_file,
    write_file,
)
from .shell import shell
from .think import think
from .todo import set_todo_list
from .web import fetch_url, search_web

# All tools
__all__ = [
    # File tools
    "read_file",
    "write_file",
    "str_replace_file",
    "glob_tool",
    "grep",
    "read_media_file",
    # Shell tool
    "shell",
    # Web tools
    "search_web",
    "fetch_url",
    # Utility tools
    "think",
    "set_todo_list",
]


def get_all_tools() -> list[Any]:
    """
    Get a list of all available tools.

    Returns:
        List of all tool functions that can be passed to an Agent's tools parameter.

    Example:
        ```python
        from agents import Agent
        from openai_agents_tools import get_all_tools

        agent = Agent(
            name="Assistant",
            tools=get_all_tools(),
        )
        ```
    """
    return [
        read_file,
        write_file,
        str_replace_file,
        glob_tool,
        grep,
        read_media_file,
        shell,
        search_web,
        fetch_url,
        think,
        set_todo_list,
    ]


def get_safe_tools() -> list[Any]:
    """
    Get a list of tools that don't require approval.

    These tools only read data and don't modify the filesystem or execute commands.

    Returns:
        List of safe tool functions.
    """
    return [
        read_file,
        glob_tool,
        grep,
        read_media_file,
        think,
        set_todo_list,
    ]


def get_file_tools() -> list[Any]:
    """
    Get a list of file operation tools.

    Returns:
        List of file tool functions.
    """
    return [
        read_file,
        write_file,
        str_replace_file,
        glob_tool,
        grep,
        read_media_file,
    ]


def get_web_tools() -> list[Any]:
    """
    Get a list of web tools.

    Note: These tools require web service configuration in the context.

    Returns:
        List of web tool functions.
    """
    return [
        search_web,
        fetch_url,
    ]
