"""
OpenAI Agents Tools - File, Shell, and Web tools for OpenAI Agents SDK.

This package provides powerful file, shell, and web tools for use with OpenAI's
Agent framework. It can be used standalone or as part of kimi-cli.

Example Usage:
    ```python
    from pathlib import Path
    from agents import Agent, Runner
    from openai_agents_tools import KimiToolContext, get_all_tools

    # Create context with your configuration
    context = KimiToolContext(
        work_dir=Path.cwd(),
        yolo_mode=True,  # Skip all approval prompts
    )

    # Create an agent with tools
    agent = Agent(
        name="FileAssistant",
        instructions="You are a helpful file assistant.",
        tools=get_all_tools(),
    )

    # Run the agent
    result = await Runner.run(agent, "Read README.md", context=context)
    print(result.final_output)
    ```

Approval Mechanism:
    Tools that modify files or execute commands require approval. You can:
    1. Set `yolo_mode=True` to skip all approvals
    2. Pre-approve specific actions via `auto_approved_actions`
    3. Provide an `approval_callback` for interactive approval

    ```python
    async def my_approval_callback(tool_name, action, description):
        print(f"{tool_name} wants to {action}: {description}")
        return input("Approve? (y/n): ").lower() == 'y'

    context = KimiToolContext(
        work_dir=Path.cwd(),
        approval_callback=my_approval_callback,
    )
    ```

Web Tools Configuration:
    Web tools (search_web, fetch_url) require service configuration:

    ```python
    from openai_agents_tools import KimiToolContext, WebServiceConfig

    context = KimiToolContext(
        work_dir=Path.cwd(),
        search_service=WebServiceConfig(
            base_url="https://api.example.com/search",
            api_key="your-api-key",
        ),
        fetch_service=WebServiceConfig(
            base_url="https://api.example.com/fetch",
            api_key="your-api-key",
        ),
    )
    ```
"""

from .context import (
    ApprovalCallback,
    KimiContext,
    KimiToolContext,
    WebServiceConfig,
)
from .errors import (
    ToolApprovalRejected,
    format_error,
    format_rejection,
    format_success,
    truncate_output,
)
from .tools import (
    fetch_url,
    get_all_tools,
    get_file_tools,
    get_safe_tools,
    get_web_tools,
    glob_tool,
    grep,
    read_file,
    read_media_file,
    search_web,
    set_todo_list,
    shell,
    str_replace_file,
    think,
    write_file,
)

__all__ = [
    # Context
    "KimiToolContext",
    "KimiContext",
    "WebServiceConfig",
    "ApprovalCallback",
    # Error utilities
    "ToolApprovalRejected",
    "format_success",
    "format_error",
    "format_rejection",
    "truncate_output",
    # Tool getters
    "get_all_tools",
    "get_safe_tools",
    "get_file_tools",
    "get_web_tools",
    # Individual tools
    "read_file",
    "write_file",
    "str_replace_file",
    "glob_tool",
    "grep",
    "read_media_file",
    "shell",
    "search_web",
    "fetch_url",
    "think",
    "set_todo_list",
]
