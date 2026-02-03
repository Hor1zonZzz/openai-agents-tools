"""
write_file - Write content to a file.

This tool writes content to files and requires approval before execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_rejection, format_success

# File action constants for approval
FILE_ACTION_EDIT = "edit file"
FILE_ACTION_EDIT_OUTSIDE = "edit file outside working directory"


class WriteFileParams(BaseModel):
    """Parameters for write_file tool."""

    path: str = Field(
        description=(
            "The path to the file to write. Absolute paths are required when writing files "
            "outside the working directory."
        )
    )
    content: str = Field(description="The content to write to the file")
    mode: Literal["overwrite", "append"] = Field(
        description=(
            "The mode to use to write to the file. "
            "Two modes are supported: `overwrite` for overwriting the whole file and "
            "`append` for appending to the end of an existing file."
        ),
        default="overwrite",
    )


def _resolve_path(path_str: str, work_dir: Path) -> tuple[Path, str | None, bool]:
    """
    Resolve and validate a file path.

    Returns:
        Tuple of (resolved_path, error_message, is_outside_workdir).
        error_message is None if valid.
    """
    try:
        p = Path(path_str).expanduser()

        # Handle relative paths
        if not p.is_absolute():
            p = work_dir / p

        p = p.resolve()

        # Check if outside work_dir
        is_outside = False
        try:
            p.relative_to(work_dir)
        except ValueError:
            is_outside = True
            # Outside work_dir - original path must be absolute
            if not Path(path_str).expanduser().is_absolute():
                return p, (
                    f"`{path_str}` is not an absolute path. "
                    "You must provide an absolute path to write a file "
                    "outside the working directory."
                ), is_outside

        return p, None, is_outside
    except Exception as e:
        return Path(path_str), f"Invalid path: {e}", False


@function_tool
async def write_file(
    ctx: RunContextWrapper[KimiToolContext], params: WriteFileParams
) -> str:
    """
    Write content to a file.

    Tips:
    - When `mode` is not specified, it defaults to `overwrite`. Always write with caution.
    - When the content to write is too long (e.g. > 100 lines), use this tool multiple
      times instead of a single call. Use `overwrite` mode the first time, then use
      `append` mode after the first write.

    This tool requires approval before execution.
    """
    work_dir = ctx.context.work_dir

    if not params.path:
        return format_error("File path cannot be empty.")

    # Resolve path
    p, error, is_outside = _resolve_path(params.path, work_dir)
    if error:
        return format_error(error)

    # Check parent directory exists
    if not p.parent.exists():
        return format_error(f"`{params.path}` parent directory does not exist.")

    # Validate mode
    if params.mode not in ["overwrite", "append"]:
        return format_error(
            f"Invalid write mode: `{params.mode}`. "
            "Mode must be either `overwrite` or `append`."
        )

    # Determine action for approval
    action = FILE_ACTION_EDIT_OUTSIDE if is_outside else FILE_ACTION_EDIT

    # Request approval
    approved = await ctx.context.request_approval(
        tool_name="write_file",
        action=action,
        description=f"Write file `{p}` (mode: {params.mode})",
    )

    if not approved:
        return format_rejection()

    try:
        # Write content
        if params.mode == "overwrite":
            p.write_text(params.content)
        else:  # append
            with open(p, "a", encoding="utf-8") as f:
                f.write(params.content)

        # Get file info for success message
        file_size = p.stat().st_size
        action_word = "overwritten" if params.mode == "overwrite" else "appended to"

        return format_success(
            "",
            f"File successfully {action_word}. Current size: {file_size} bytes.",
        )

    except Exception as e:
        return format_error(f"Failed to write to {params.path}. Error: {e}")
