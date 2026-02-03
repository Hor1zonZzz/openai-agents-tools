"""
str_replace_file - Replace specific strings within a file.

This tool performs string replacements in files and requires approval before execution.
"""

from __future__ import annotations

from pathlib import Path

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_rejection, format_success

# File action constants for approval
FILE_ACTION_EDIT = "edit file"
FILE_ACTION_EDIT_OUTSIDE = "edit file outside working directory"


class Edit(BaseModel):
    """A single edit operation."""

    old: str = Field(description="The old string to replace. Can be multi-line.")
    new: str = Field(description="The new string to replace with. Can be multi-line.")
    replace_all: bool = Field(
        description="Whether to replace all occurrences.", default=False
    )


class StrReplaceFileParams(BaseModel):
    """Parameters for str_replace_file tool."""

    path: str = Field(
        description=(
            "The path to the file to edit. Absolute paths are required when editing files "
            "outside the working directory."
        )
    )
    edit: Edit | list[Edit] = Field(
        description=(
            "The edit(s) to apply to the file. "
            "You can provide a single edit or a list of edits here."
        )
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
                    "You must provide an absolute path to edit a file "
                    "outside the working directory."
                ), is_outside

        return p, None, is_outside
    except Exception as e:
        return Path(path_str), f"Invalid path: {e}", False


def _apply_edit(content: str, edit: Edit) -> str:
    """Apply a single edit to the content."""
    if edit.replace_all:
        return content.replace(edit.old, edit.new)
    else:
        return content.replace(edit.old, edit.new, 1)


@function_tool
async def str_replace_file(
    ctx: RunContextWrapper[KimiToolContext], params: StrReplaceFileParams
) -> str:
    """
    Replace specific strings within a specified file.

    Tips:
    - Only use this tool on text files.
    - Multi-line strings are supported.
    - Can specify a single edit or a list of edits in one call.
    - You should prefer this tool over write_file tool and shell `sed` command.

    This tool requires approval before execution.
    """
    work_dir = ctx.context.work_dir

    if not params.path:
        return format_error("File path cannot be empty.")

    # Resolve path
    p, error, is_outside = _resolve_path(params.path, work_dir)
    if error:
        return format_error(error)

    # Check file exists
    if not p.exists():
        return format_error(f"`{params.path}` does not exist.")
    if not p.is_file():
        return format_error(f"`{params.path}` is not a file.")

    try:
        # Read the file content
        content = p.read_text(errors="replace")
        original_content = content

        # Normalize edits to a list
        edits = [params.edit] if isinstance(params.edit, Edit) else params.edit

        # Apply all edits
        for edit in edits:
            content = _apply_edit(content, edit)

        # Check if any changes were made
        if content == original_content:
            return format_error(
                "No replacements were made. The old string was not found in the file."
            )

        # Determine action for approval
        action = FILE_ACTION_EDIT_OUTSIDE if is_outside else FILE_ACTION_EDIT

        # Request approval
        approved = await ctx.context.request_approval(
            tool_name="str_replace_file",
            action=action,
            description=f"Edit file `{p}` with {len(edits)} edit(s)",
        )

        if not approved:
            return format_rejection()

        # Write the modified content back
        p.write_text(content)

        # Count changes for success message
        total_replacements = 0
        for edit in edits:
            if edit.replace_all:
                total_replacements += original_content.count(edit.old)
            else:
                total_replacements += 1 if edit.old in original_content else 0

        return format_success(
            "",
            f"File successfully edited. "
            f"Applied {len(edits)} edit(s) with {total_replacements} total replacement(s).",
        )

    except Exception as e:
        return format_error(f"Failed to edit. Error: {e}")
