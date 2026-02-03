"""
fetch_url - Fetch a web page and extract its content.

This tool fetches web pages and extracts the main text content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext, WebServiceConfig
from ...errors import format_error, format_success, truncate_output

if TYPE_CHECKING:
    pass

# Try to import required libraries
try:
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import trafilatura

    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


class FetchURLParams(BaseModel):
    """Parameters for fetch_url tool."""

    url: str = Field(description="The URL to fetch content from.")


@function_tool
async def fetch_url(
    ctx: RunContextWrapper[KimiToolContext], params: FetchURLParams
) -> str:
    """
    Fetch a web page from a URL and extract main text content from it.

    This tool:
    1. Fetches the web page content
    2. Extracts the main text content (removes navigation, ads, etc.)
    3. Returns the extracted text

    For plain text or markdown URLs, the content is returned as-is.

    Note: If a fetch service is configured in the context, it will be tried first.
    If it fails or is not configured, a direct HTTP fetch will be attempted.
    """
    if not HAS_AIOHTTP:
        return format_error(
            "aiohttp is not installed. Install it with: pip install aiohttp"
        )

    # Try fetch service first if configured
    fetch_config = ctx.context.fetch_service
    if fetch_config is not None and fetch_config.base_url and fetch_config.api_key:
        result = await _fetch_with_service(params.url, fetch_config)
        if not result.startswith("Error:"):
            return result

    # Fall back to direct fetch
    return await _fetch_with_http_get(params.url)


async def _fetch_with_service(url: str, config: WebServiceConfig) -> str:
    """Fetch URL using a configured fetch service."""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": "kimi-cli/openai-agents",
                "Authorization": f"Bearer {config.api_key}",
                "Accept": "text/markdown",
                **config.custom_headers,
            }

            async with session.post(
                config.base_url,
                headers=headers,
                json={"url": url},
            ) as response:
                if response.status != 200:
                    return format_error(
                        f"Failed to fetch URL via service. Status: {response.status}."
                    )

                content = await response.text()
                content, was_truncated = truncate_output(content, max_line_length=None)

                message = "The returned content is the main content extracted from the page."
                if was_truncated:
                    message += " (output truncated)"

                return format_success(content, message)

    except aiohttp.ClientError as e:
        return format_error(f"Network error when calling fetch service: {e}")


async def _fetch_with_http_get(url: str) -> str:
    """Fetch URL using direct HTTP GET request."""
    resp_text = ""
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers={"User-Agent": USER_AGENT}) as response,
        ):
            if response.status >= 400:
                return format_error(
                    f"Failed to fetch URL. Status: {response.status}. "
                    "This may indicate the page is not accessible or the server is down."
                )

            resp_text = await response.text()

            # Check content type
            content_type = response.headers.get(aiohttp.hdrs.CONTENT_TYPE, "").lower()
            if content_type.startswith(("text/plain", "text/markdown")):
                content, was_truncated = truncate_output(resp_text, max_line_length=None)
                message = "The returned content is the full content of the page."
                if was_truncated:
                    message += " (output truncated)"
                return format_success(content, message)

    except aiohttp.ClientError as e:
        return format_error(
            f"Failed to fetch URL due to network error: {e}. "
            "This may indicate the URL is invalid or the server is unreachable."
        )

    if not resp_text:
        return format_success("", "The response body is empty.")

    # Extract text content using trafilatura
    if not HAS_TRAFILATURA:
        # If trafilatura is not available, return raw HTML truncated
        content, was_truncated = truncate_output(resp_text, max_line_length=None)
        message = (
            "trafilatura is not installed, returning raw HTML. "
            "Install it with: pip install trafilatura"
        )
        if was_truncated:
            message += " (output truncated)"
        return format_success(content, message)

    extracted_text = trafilatura.extract(
        resp_text,
        include_comments=True,
        include_tables=True,
        include_formatting=False,
        output_format="txt",
        with_metadata=True,
    )

    if not extracted_text:
        return format_error(
            "Failed to extract meaningful content from the page. "
            "This may indicate the page content is not suitable for text extraction, "
            "or the page requires JavaScript to render its content."
        )

    content, was_truncated = truncate_output(extracted_text, max_line_length=None)
    message = "The returned content is the main text content extracted from the page."
    if was_truncated:
        message += " (output truncated)"

    return format_success(content, message)
