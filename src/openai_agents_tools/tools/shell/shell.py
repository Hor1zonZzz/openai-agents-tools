"""
shell - Execute shell commands.

This tool executes shell commands and requires approval before execution.
"""

from __future__ import annotations

import asyncio
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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


@dataclass(frozen=True)
class ShellInfo:
    """Information about the detected shell."""

    name: Literal["bash", "sh", "powershell", "cmd"]
    path: str

    @property
    def is_powershell(self) -> bool:
        return self.name == "powershell"

    @property
    def is_cmd(self) -> bool:
        return self.name == "cmd"

    def get_args(self, command: str) -> tuple[str, ...]:
        """
        Get the shell arguments for executing a command.

        This mirrors kimi-cli's _shell_args method:
        - PowerShell: (shell_path, "-Command", command)
        - cmd: (shell_path, "/c", command)
        - bash/sh: (shell_path, "-c", command)
        """
        if self.is_powershell:
            return (self.path, "-Command", command)
        elif self.is_cmd:
            return (self.path, "/c", command)
        else:
            # bash or sh
            return (self.path, "-c", command)


def _detect_shell() -> ShellInfo:
    """
    Detect the default shell for the current platform.

    This mirrors kimi-cli's Environment.detect() logic:
    - Windows: PowerShell (preferred) or cmd
    - Unix: bash (preferred) or sh

    Returns:
        ShellInfo with name and path.
    """
    system = platform.system()

    if system == "Windows":
        # Windows: prefer PowerShell, fall back to cmd
        # Note: kimi-cli uses "powershell.exe" directly
        powershell = shutil.which("powershell")
        if powershell:
            return ShellInfo(name="powershell", path=powershell)

        cmd = shutil.which("cmd")
        if cmd:
            return ShellInfo(name="cmd", path=cmd)

        # Fallback to cmd.exe
        return ShellInfo(name="cmd", path="cmd.exe")
    else:
        # Unix-like: prefer bash, fall back to sh
        # Check common bash paths like kimi-cli does
        bash_paths = [
            Path("/bin/bash"),
            Path("/usr/bin/bash"),
            Path("/usr/local/bin/bash"),
        ]

        for bash_path in bash_paths:
            if bash_path.is_file():
                return ShellInfo(name="bash", path=str(bash_path))

        # Try shutil.which as fallback
        bash = shutil.which("bash")
        if bash:
            return ShellInfo(name="bash", path=bash)

        # Fall back to sh
        sh = shutil.which("sh")
        if sh:
            return ShellInfo(name="sh", path=sh)

        return ShellInfo(name="sh", path="/bin/sh")


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

    # Detect shell and get execution arguments
    shell_info = _detect_shell()
    shell_args = shell_info.get_args(params.command)

    try:
        # Create subprocess with explicit arguments (like kimi-cli's kaos.exec)
        # This ensures correct behavior for PowerShell (-Command) vs bash (-c)
        process = await asyncio.create_subprocess_exec(
            *shell_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ctx.context.work_dir),
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
