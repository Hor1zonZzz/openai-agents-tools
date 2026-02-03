"""
search_web - Search the internet for information.

This tool searches the web using a configurable search service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_success, truncate_output

if TYPE_CHECKING:
    pass

# Try to import aiohttp
try:
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

USER_AGENT = "kimi-cli/openai-agents"


class SearchWebParams(BaseModel):
    """Parameters for search_web tool."""

    query: str = Field(description="The query text to search for.")
    limit: int = Field(
        description=(
            "The number of results to return. "
            "Typically you do not need to set this value. "
            "When the results do not contain what you need, "
            "you probably want to give a more concrete query."
        ),
        default=5,
        ge=1,
        le=20,
    )
    include_content: bool = Field(
        description=(
            "Whether to include the content of the web pages in the results. "
            "It can consume a large amount of tokens when this is set to True. "
            "You should avoid enabling this when `limit` is set to a large value."
        ),
        default=False,
    )


class SearchResult(BaseModel):
    """A single search result."""

    site_name: str
    title: str
    url: str
    snippet: str
    content: str = ""
    date: str = ""


class SearchResponse(BaseModel):
    """Response from search service."""

    search_results: list[SearchResult]


@function_tool
async def search_web(
    ctx: RunContextWrapper[KimiToolContext], params: SearchWebParams
) -> str:
    """
    Search the internet to get latest information.

    This tool allows you to search for news, documents, release notes,
    blog posts, papers, and other web content.

    Note: This tool requires a configured search service in the context.
    If no search service is configured, the tool will return an error.
    """
    if not HAS_AIOHTTP:
        return format_error(
            "aiohttp is not installed. Install it with: pip install aiohttp"
        )

    # Check if search service is configured
    search_config = ctx.context.search_service
    if search_config is None:
        return format_error(
            "Search service is not configured. "
            "You need to provide a search_service configuration in the context."
        )

    if not search_config.base_url or not search_config.api_key:
        return format_error(
            "Search service is not properly configured. "
            "You may want to try other methods to search."
        )

    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {search_config.api_key}",
                **search_config.custom_headers,
            }

            async with session.post(
                search_config.base_url,
                headers=headers,
                json={
                    "text_query": params.query,
                    "limit": params.limit,
                    "enable_page_crawling": params.include_content,
                    "timeout_seconds": 30,
                },
            ) as response:
                if response.status != 200:
                    return format_error(
                        f"Failed to search. Status: {response.status}. "
                        "This may indicate that the search service is currently unavailable."
                    )

                data = await response.json()

                try:
                    search_response = SearchResponse(**data)
                    results = search_response.search_results
                except Exception as e:
                    return format_error(
                        f"Failed to parse search results. Error: {e}. "
                        "This may indicate that the search service is currently unavailable."
                    )

        # Format results
        output_lines: list[str] = []
        for i, result in enumerate(results):
            if i > 0:
                output_lines.append("---\n")
            output_lines.append(
                f"Title: {result.title}\n"
                f"Date: {result.date}\n"
                f"URL: {result.url}\n"
                f"Summary: {result.snippet}\n"
            )
            if result.content:
                output_lines.append(f"\n{result.content}\n")

        output = "\n".join(output_lines)
        output, was_truncated = truncate_output(output, max_line_length=None)

        message = f"Found {len(results)} results for query: {params.query}"
        if was_truncated:
            message += " (output truncated)"

        return format_success(output, message)

    except aiohttp.ClientError as e:
        return format_error(f"Network error while searching: {e}")
    except Exception as e:
        return format_error(f"Failed to search. Error: {e}")
