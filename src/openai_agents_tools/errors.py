"""
Error handling utilities for OpenAI Agents SDK tools.

This module provides utilities to convert between KIMI CLI's ToolReturnValue format
and the OpenAI Agents SDK's string-based return format.
"""

from __future__ import annotations


class ToolApprovalRejected(Exception):
    """
    Exception raised when a tool operation is rejected by the user.

    When raised, this tells the agent that the operation was not approved
    and it should follow new instructions from the user.
    """

    def __init__(self, message: str = "Operation rejected by user"):
        super().__init__(message)
        self.message = message


def format_success(output: str, message: str = "") -> str:
    """
    Format a successful tool result.

    Args:
        output: The main output content
        message: Optional explanatory message

    Returns:
        Formatted string for the agent
    """
    if not output and not message:
        return "Operation completed successfully."

    if not message:
        return output

    if not output:
        return message

    return f"{output}\n\n[{message}]"


def format_error(message: str) -> str:
    """
    Format an error message.

    Args:
        message: The error message

    Returns:
        Formatted error string for the agent
    """
    return f"Error: {message}"


def format_rejection() -> str:
    """
    Format a rejection message when user denies approval.

    Returns:
        Formatted rejection string for the agent
    """
    return (
        "Error: The tool call is rejected by the user. "
        "Please follow the new instructions from the user."
    )


# Output limits (matching KIMI CLI defaults)
DEFAULT_MAX_CHARS = 50_000
DEFAULT_MAX_LINE_LENGTH = 2000


def truncate_output(
    output: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    max_line_length: int | None = DEFAULT_MAX_LINE_LENGTH,
) -> tuple[str, bool]:
    """
    Truncate output to fit within limits.

    Args:
        output: The output string to truncate
        max_chars: Maximum total characters
        max_line_length: Maximum length per line (None for no limit)

    Returns:
        Tuple of (truncated_output, was_truncated)
    """
    if not output:
        return output, False

    truncated = False
    lines = output.splitlines(keepends=True)
    result_lines: list[str] = []
    total_chars = 0

    for line in lines:
        # Check total character limit
        if total_chars >= max_chars:
            truncated = True
            break

        # Truncate line if needed
        if max_line_length is not None and len(line) > max_line_length:
            line = line[: max_line_length - 3] + "..."
            if not line.endswith("\n") and output.count("\n") > 0:
                line += "\n"
            truncated = True

        # Check if adding this line exceeds limit
        if total_chars + len(line) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 3:
                line = line[: remaining - 3] + "..."
            else:
                break
            truncated = True

        result_lines.append(line)
        total_chars += len(line)

    result = "".join(result_lines)

    if truncated:
        if not result.endswith("\n"):
            result += "\n"
        result += "[...truncated]"

    return result, truncated
