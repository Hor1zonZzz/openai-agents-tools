"""
KimiToolContext - Runtime context for OpenAI Agents SDK tools.

This module provides the context object that carries runtime configuration
for tools, including working directory, approval settings, and web service configs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class ApprovalCallback(Protocol):
    """Protocol for approval callback functions."""

    async def __call__(
        self,
        tool_name: str,
        action: str,
        description: str,
    ) -> bool:
        """
        Request approval for a tool action.

        Args:
            tool_name: Name of the tool requesting approval
            action: Type of action being performed (e.g., "run command", "edit file")
            description: Human-readable description of what will be done

        Returns:
            True if approved, False if rejected
        """
        ...


@dataclass
class WebServiceConfig:
    """Configuration for web services (search/fetch)."""

    base_url: str
    api_key: str
    custom_headers: dict[str, str] = field(default_factory=dict)


@dataclass
class KimiToolContext:
    """
    Runtime context for KIMI tools in OpenAI Agents SDK.

    This context is passed to tools via RunContextWrapper.context and provides:
    - Working directory configuration
    - Approval mechanism for dangerous operations
    - Web service configuration (optional)

    Example:
        ```python
        from agents import Agent, Runner
        from openai_agents_tools import KimiToolContext, get_all_tools

        context = KimiToolContext(
            work_dir=Path.cwd(),
            yolo_mode=True,  # Skip all approvals
        )

        agent = Agent(
            name="FileAssistant",
            tools=get_all_tools(),
        )

        result = await Runner.run(agent, "Read README.md", context=context)
        ```
    """

    work_dir: Path
    """The working directory for file operations."""

    yolo_mode: bool = False
    """If True, skip all approval prompts."""

    auto_approved_actions: set[str] = field(default_factory=set)
    """Set of action names that are automatically approved."""

    approval_callback: ApprovalCallback | None = None
    """
    Optional callback for requesting user approval.
    If None and yolo_mode is False, dangerous operations will be rejected.
    """

    # Web service configurations (optional)
    search_service: WebServiceConfig | None = None
    """Configuration for web search service."""

    fetch_service: WebServiceConfig | None = None
    """Configuration for URL fetch service."""

    async def request_approval(
        self,
        tool_name: str,
        action: str,
        description: str,
    ) -> bool:
        """
        Request approval for a potentially dangerous operation.

        Args:
            tool_name: Name of the tool requesting approval
            action: Type of action (used for auto-approval matching)
            description: Human-readable description of the action

        Returns:
            True if the action is approved, False otherwise
        """
        # YOLO mode: approve everything
        if self.yolo_mode:
            return True

        # Check auto-approved actions
        if action in self.auto_approved_actions:
            return True

        # Use callback if provided
        if self.approval_callback is not None:
            return await self.approval_callback(tool_name, action, description)

        # No callback and not auto-approved: reject
        return False

    def approve_action(self, action: str) -> None:
        """Add an action to the auto-approved set."""
        self.auto_approved_actions.add(action)


# Type alias for convenience - use Any since agents SDK may not be installed
# When agents SDK is installed, you can use: RunContextWrapper[KimiToolContext]
type KimiContext = Any
