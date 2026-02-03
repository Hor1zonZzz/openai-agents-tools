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

from agents import RunContextWrapper, Tool
from agents.tool import FunctionTool
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

    @property
    def is_windows(self) -> bool:
        return self.is_powershell or self.is_cmd

    @property
    def display_name(self) -> str:
        """Get human-readable shell name for prompts."""
        if self.is_powershell:
            return "Windows PowerShell"
        elif self.is_cmd:
            return "Windows cmd"
        elif self.name == "bash":
            return "bash"
        else:
            return "sh"

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


def _load_description(shell_info: ShellInfo) -> str:
    """
    Load the tool description from a markdown file.

    This mirrors kimi-cli's load_desc() function:
    - Loads bash.md or powershell.md based on shell type
    - Replaces ${SHELL} with the actual shell name and path

    Args:
        shell_info: The detected shell information.

    Returns:
        The tool description with variables replaced.
    """
    # Determine which description file to use
    desc_file = "powershell.md" if shell_info.is_windows else "bash.md"

    # Load the description file
    desc_path = Path(__file__).parent / desc_file

    try:
        description = desc_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Fallback to a basic description if file not found
        return (
            f"Execute a {shell_info.display_name} command. "
            "Use this tool to explore the filesystem, run scripts, etc."
        )

    # Replace template variables (like kimi-cli's Jinja2 replacement)
    shell_display = f"{shell_info.display_name} (`{shell_info.path}`)"
    description = description.replace("${SHELL}", shell_display)

    return description


# Detect shell at module load time
_shell_info = _detect_shell()


async def _shell_handler(
    ctx: RunContextWrapper[KimiToolContext], args: str
) -> str:
    """
    The actual shell command handler.

    This is called by the FunctionTool when the tool is invoked.
    """
    import json

    # Parse arguments
    try:
        params_dict = json.loads(args)
        params = ShellParams.model_validate(params_dict)
    except Exception as e:
        return format_error(f"Invalid parameters: {e}")

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

    # Get shell arguments
    shell_args = _shell_info.get_args(params.command)

    try:
        # Create subprocess with explicit arguments (like kimi-cli's kaos.exec)
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


def create_shell_tool() -> Tool:
    """
    Create the shell tool with dynamically loaded description.

    This mirrors kimi-cli's approach of loading description from
    bash.md or powershell.md based on the detected shell.

    Returns:
        A FunctionTool configured for the current platform's shell.
    """
    description = _load_description(_shell_info)

    # Generate JSON schema from Pydantic model
    params_schema = ShellParams.model_json_schema()

    return FunctionTool(
        name="shell",
        description=description,
        params_json_schema=params_schema,
        on_invoke_tool=_shell_handler,
    )


# Create the shell tool instance
# This is what gets exported and used
shell = create_shell_tool()


def get_shell_info() -> ShellInfo:
    """
    Get information about the detected shell.

    Useful for debugging or conditional logic based on shell type.
    """
    return _shell_info
