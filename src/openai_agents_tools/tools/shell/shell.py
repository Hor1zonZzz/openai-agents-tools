"""
shell - Execute shell commands.

This tool executes shell commands and requires approval before execution.
"""

from __future__ import annotations

import asyncio
import platform
import shutil

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import (
    format_error,
    format_rejection,
    format_success,
    truncate_output,
)

MAX_TIMEOUT = 5 * 60  # 5 minutes


class ShellParams(BaseModel):
    """Parameters for shell tool."""

    command: str = Field(description="The shell command to execute.")
    timeout: int = Field(
        description=(
            "The timeout in seconds for the command to execute. "
            "If the command takes longer than this, it will be killed."
        ),
        default=60,
        ge=1,
        le=MAX_TIMEOUT,
    )


def _get_default_shell() -> str:
    """
    Get the default shell path for the current platform.

    Returns:
        Path to the default shell executable.
    """
    system = platform.system()

    if system == "Windows":
        # Try PowerShell first, fall back to cmd
        powershell = shutil.which("powershell")
        if powershell:
            return powershell
        cmd = shutil.which("cmd")
        if cmd:
            return cmd
        return "cmd"
    else:
        # Unix-like systems
        return shutil.which("bash") or shutil.which("sh") or "/bin/sh"


@function_tool
async def shell(
    ctx: RunContextWrapper[KimiToolContext], params: ShellParams
) -> str:
    """
    Execute a shell command.

    Use this tool to explore the filesystem, run scripts, get system information, etc.

    Output:
    The stdout and stderr will be combined and returned. The output may be truncated
    if it is too long. If the command failed, the exit code will be provided.

    Guidelines for safety:
    - Each shell tool call executes in a fresh shell environment
    - Shell variables and current working directory are not preserved between calls
    - Set `timeout` to a reasonable value for possibly long-running commands
    - Avoid using `..` to access files outside the working directory
    - Avoid modifying files outside the working directory unless explicitly instructed
    - Never run commands requiring superuser privileges unless explicitly instructed

    Guidelines for efficiency:
    - Use `&&` to chain related commands: `cd /path && ls -la`
    - Use `;` to run commands sequentially regardless of success/failure
    - Use `||` for conditional execution (run second only if first fails)
    - Use pipes (`|`) and redirections (`>`, `>>`) to chain commands
    - Always quote file paths containing spaces with double quotes

    This tool requires approval before execution.
    """
    if not params.command:
        return format_error("Command cannot be empty.")

    # Request approval
    approved = await ctx.context.request_approval(
        tool_name="shell",
        action="run command",
        description=f"Run command `{params.command}`",
    )

    if not approved:
        return format_rejection()

    # Get shell path
    shell_path = _get_default_shell()

    try:
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            params.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ctx.context.work_dir),
            shell=True,
            executable=shell_path if platform.system() != "Windows" else None,
        )

        try:
            # Wait for process with timeout
            stdout, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=params.timeout,
            )
        except TimeoutError:
            # Kill the process on timeout
            process.kill()
            await process.wait()
            return format_error(f"Command killed by timeout ({params.timeout}s)")

        # Decode output
        output = stdout.decode("utf-8", errors="replace")

        # Truncate if needed
        output, was_truncated = truncate_output(output)

        # Build result based on exit code
        exitcode = process.returncode

        if exitcode == 0:
            message = "Command executed successfully."
            if was_truncated:
                message += " Output was truncated."
            return format_success(output, message)
        else:
            message = f"Command failed with exit code: {exitcode}."
            if was_truncated:
                message += " Output was truncated."
            return format_error(f"{message}\n\nOutput:\n{output}")

    except Exception as e:
        return format_error(f"Failed to execute command. Error: {e}")
