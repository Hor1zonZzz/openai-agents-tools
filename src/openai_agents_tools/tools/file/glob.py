"""
glob_tool - Find files and directories using glob patterns.

This tool supports standard glob syntax like `*`, `?`, and `**` for recursive searches.
"""

from __future__ import annotations

from pathlib import Path

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_success

MAX_MATCHES = 1000


class GlobParams(BaseModel):
    """Parameters for glob_tool."""

    pattern: str = Field(description="Glob pattern to match files/directories.")
    directory: str | None = Field(
        description=(
            "Absolute path to the directory to search in (defaults to working directory)."
        ),
        default=None,
    )
    include_dirs: bool = Field(
        description="Whether to include directories in results.",
        default=True,
    )


def _list_directory(path: Path) -> str:
    """List contents of a directory for helpful error messages."""
    try:
        items = sorted(path.iterdir())
        dirs = [f"  {p.name}/" for p in items if p.is_dir()]
        files = [f"  {p.name}" for p in items if p.is_file()]
        return "\n".join(dirs + files)
    except Exception:
        return "(unable to list directory)"


@function_tool
async def glob_tool(
    ctx: RunContextWrapper[KimiToolContext], params: GlobParams
) -> str:
    """
    Find files and directories using glob patterns.

    Supports standard glob syntax:
    - `*` - Match any characters in a single path segment
    - `?` - Match any single character
    - `**` - Match any characters across path segments (recursive)
    - `{a,b}` - Match either pattern a or b

    Example patterns:
    - `*.py` - All Python files in current directory
    - `src/**/*.js` - All JavaScript files in src directory recursively
    - `test_*.py` - Python test files starting with "test_"
    - `*.config.{js,ts}` - Config files with .js or .ts extension

    Note: Patterns starting with '**' are rejected as they may return too many results.
    """
    work_dir = ctx.context.work_dir

    # Validate pattern safety
    if params.pattern.startswith("**"):
        ls_result = _list_directory(work_dir)
        return format_error(
            f"Pattern `{params.pattern}` starts with '**' which is not allowed. "
            "This would recursively search all directories and may include large "
            "directories like `node_modules`. Use more specific patterns instead.\n\n"
            f"Top-level directory contents:\n{ls_result}"
        )

    # Determine search directory
    if params.directory:
        dir_path = Path(params.directory)
        if not dir_path.is_absolute():
            return format_error(
                f"`{params.directory}` is not an absolute path. "
                "You must provide an absolute path to search."
            )
    else:
        dir_path = work_dir

    # Check directory exists
    if not dir_path.exists():
        return format_error(f"`{params.directory}` does not exist.")
    if not dir_path.is_dir():
        return format_error(f"`{params.directory}` is not a directory.")

    try:
        # Perform the glob search
        matches: list[Path] = list(dir_path.glob(params.pattern))

        # Filter out directories if not requested
        if not params.include_dirs:
            matches = [p for p in matches if p.is_file()]

        # Sort for consistent output
        matches.sort()

        # Build message
        message = (
            f"Found {len(matches)} matches for pattern `{params.pattern}`."
            if len(matches) > 0
            else f"No matches found for pattern `{params.pattern}`."
        )

        # Limit matches
        if len(matches) > MAX_MATCHES:
            matches = matches[:MAX_MATCHES]
            message += (
                f" Only the first {MAX_MATCHES} matches are returned. "
                "You may want to use a more specific pattern."
            )

        # Format output as relative paths
        output = "\n".join(str(p.relative_to(dir_path)) for p in matches)

        return format_success(output, message)

    except Exception as e:
        return format_error(f"Failed to search for pattern {params.pattern}. Error: {e}")
