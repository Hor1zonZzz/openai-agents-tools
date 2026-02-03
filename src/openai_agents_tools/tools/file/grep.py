"""
grep - A powerful search tool based on ripgrep.

This tool provides fast regex-based content search across files.
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Literal

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_success

# Try to import ripgrepy, provide fallback if not available
try:
    import ripgrepy  # type: ignore[import]

    HAS_RIPGREPY = True
except ImportError:
    HAS_RIPGREPY = False
    ripgrepy = None

# Try to import aiohttp for downloading rg
try:
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False


RG_VERSION = "15.0.0"
RG_BASE_URL = "http://cdn.kimi.com/binaries/kimi-cli/rg"
_RG_DOWNLOAD_LOCK = asyncio.Lock()


class GrepParams(BaseModel):
    """Parameters for grep tool."""

    pattern: str = Field(
        description="The regular expression pattern to search for in file contents"
    )
    path: str = Field(
        description=(
            "File or directory to search in. Defaults to current working directory. "
            "If specified, it must be an absolute path."
        ),
        default=".",
    )
    glob: str | None = Field(
        description=(
            "Glob pattern to filter files (e.g. `*.js`, `*.{ts,tsx}`). No filter by default."
        ),
        default=None,
    )
    output_mode: Literal["content", "files_with_matches", "count_matches"] = Field(
        description=(
            "`content`: Show matching lines (supports `-B`, `-A`, `-C`, `-n`, `head_limit`); "
            "`files_with_matches`: Show file paths (supports `head_limit`); "
            "`count_matches`: Show total number of matches. "
            "Defaults to `files_with_matches`."
        ),
        default="files_with_matches",
    )
    before_context: int | None = Field(
        alias="-B",
        description=(
            "Number of lines to show before each match (the `-B` option). "
            "Requires `output_mode` to be `content`."
        ),
        default=None,
    )
    after_context: int | None = Field(
        alias="-A",
        description=(
            "Number of lines to show after each match (the `-A` option). "
            "Requires `output_mode` to be `content`."
        ),
        default=None,
    )
    context: int | None = Field(
        alias="-C",
        description=(
            "Number of lines to show before and after each match (the `-C` option). "
            "Requires `output_mode` to be `content`."
        ),
        default=None,
    )
    line_number: bool = Field(
        alias="-n",
        description=(
            "Show line numbers in output (the `-n` option). Requires `output_mode` to be `content`."
        ),
        default=False,
    )
    ignore_case: bool = Field(
        alias="-i",
        description="Case insensitive search (the `-i` option).",
        default=False,
    )
    type: str | None = Field(
        description=(
            "File type to search. Examples: py, rust, js, ts, go, java, etc. "
            "More efficient than `glob` for standard file types."
        ),
        default=None,
    )
    head_limit: int | None = Field(
        description=(
            "Limit output to first N lines, equivalent to `| head -N`. "
            "Works across all output modes: content (limits output lines), "
            "files_with_matches (limits file paths), count_matches (limits count entries). "
            "By default, no limit is applied."
        ),
        default=None,
    )
    multiline: bool = Field(
        description=(
            "Enable multiline mode where `.` matches newlines and patterns can span "
            "lines (the `-U` and `--multiline-dotall` options). "
            "By default, multiline mode is disabled."
        ),
        default=False,
    )


def _rg_binary_name() -> str:
    return "rg.exe" if platform.system() == "Windows" else "rg"


def _get_share_dir() -> Path:
    """Get the kimi share directory."""
    return Path.home() / ".local" / "share" / "kimi"


def _find_existing_rg(bin_name: str) -> Path | None:
    """Find an existing ripgrep binary."""
    share_bin = _get_share_dir() / "bin" / bin_name
    if share_bin.is_file():
        return share_bin

    system_rg = shutil.which("rg")
    if system_rg:
        return Path(system_rg)

    return None


def _detect_target() -> str | None:
    """Detect the platform target for ripgrep download."""
    sys_name = platform.system()
    mach = platform.machine().lower()

    if mach in ("x86_64", "amd64"):
        arch = "x86_64"
    elif mach in ("arm64", "aarch64"):
        arch = "aarch64"
    else:
        return None

    if sys_name == "Darwin":
        os_name = "apple-darwin"
    elif sys_name == "Linux":
        os_name = "unknown-linux-musl" if arch == "x86_64" else "unknown-linux-gnu"
    elif sys_name == "Windows":
        os_name = "pc-windows-msvc"
    else:
        return None

    return f"{arch}-{os_name}"


async def _download_and_install_rg(bin_name: str) -> Path:
    """Download and install ripgrep binary."""
    if not HAS_AIOHTTP:
        raise RuntimeError("aiohttp is required to download ripgrep")

    target = _detect_target()
    if not target:
        raise RuntimeError("Unsupported platform for ripgrep download")

    is_windows = "windows" in target
    archive_ext = "zip" if is_windows else "tar.gz"
    filename = f"ripgrep-{RG_VERSION}-{target}.{archive_ext}"
    url = f"{RG_BASE_URL}/{filename}"

    share_bin_dir = _get_share_dir() / "bin"
    share_bin_dir.mkdir(parents=True, exist_ok=True)
    destination = share_bin_dir / bin_name

    async with aiohttp.ClientSession() as session:
        with tempfile.TemporaryDirectory(prefix="kimi-rg-") as tmpdir:
            tar_path = Path(tmpdir) / filename

            async with session.get(url) as resp:
                resp.raise_for_status()
                with open(tar_path, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        if chunk:
                            fh.write(chunk)

            if is_windows:
                with zipfile.ZipFile(tar_path, "r") as zf:
                    member_name = next(
                        (name for name in zf.namelist() if Path(name).name == bin_name),
                        None,
                    )
                    if not member_name:
                        raise RuntimeError("Ripgrep binary not found in archive")
                    with zf.open(member_name) as source, open(destination, "wb") as dest_fh:
                        shutil.copyfileobj(source, dest_fh)
            else:
                with tarfile.open(tar_path, "r:gz") as tar:
                    member = next(
                        (m for m in tar.getmembers() if Path(m.name).name == bin_name),
                        None,
                    )
                    if not member:
                        raise RuntimeError("Ripgrep binary not found in archive")
                    extracted = tar.extractfile(member)
                    if not extracted:
                        raise RuntimeError("Failed to extract ripgrep binary")
                    with open(destination, "wb") as dest_fh:
                        shutil.copyfileobj(extracted, dest_fh)

    destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return destination


async def _ensure_rg_path() -> str:
    """Ensure ripgrep is available and return its path."""
    bin_name = _rg_binary_name()
    existing = _find_existing_rg(bin_name)
    if existing:
        return str(existing)

    async with _RG_DOWNLOAD_LOCK:
        existing = _find_existing_rg(bin_name)
        if existing:
            return str(existing)

        downloaded = await _download_and_install_rg(bin_name)
        return str(downloaded)


@function_tool
async def grep(
    ctx: RunContextWrapper[KimiToolContext], params: GrepParams
) -> str:
    """
    A powerful search tool based on ripgrep.

    Tips:
    - ALWAYS use grep tool instead of running `grep` or `rg` command with shell tool.
    - Use ripgrep pattern syntax, not grep syntax. E.g. escape braces like `\\{` to search for `{`.
    - Use `output_mode="content"` to see actual matching lines.
    - Use `output_mode="files_with_matches"` (default) to see just file paths.
    """
    if not HAS_RIPGREPY:
        return format_error(
            "ripgrepy is not installed. Install it with: pip install ripgrepy"
        )

    work_dir = ctx.context.work_dir

    # Resolve search path
    search_path = params.path
    if search_path == ".":
        search_path = str(work_dir)
    elif not Path(search_path).is_absolute():
        search_path = str(work_dir / search_path)

    try:
        # Ensure ripgrep is available
        rg_path = await _ensure_rg_path()

        # Initialize ripgrep
        rg = ripgrepy.Ripgrepy(params.pattern, search_path, rg_path=rg_path)

        # Apply search options
        if params.ignore_case:
            rg = rg.ignore_case()
        if params.multiline:
            rg = rg.multiline().multiline_dotall()

        # Content display options (only for content mode)
        if params.output_mode == "content":
            if params.before_context is not None:
                rg = rg.before_context(params.before_context)
            if params.after_context is not None:
                rg = rg.after_context(params.after_context)
            if params.context is not None:
                rg = rg.context(params.context)
            if params.line_number:
                rg = rg.line_number()

        # File filtering options
        if params.glob:
            rg = rg.glob(params.glob)
        if params.type:
            rg = rg.type_(params.type)

        # Set output mode
        if params.output_mode == "files_with_matches":
            rg = rg.files_with_matches()
        elif params.output_mode == "count_matches":
            rg = rg.count_matches()

        # Execute search
        result = rg.run(universal_newlines=False)
        output = result.as_string

        # Apply head limit if specified
        message = ""
        if params.head_limit is not None and output:
            lines = output.split("\n")
            if len(lines) > params.head_limit:
                lines = lines[: params.head_limit]
                output = "\n".join(lines)
                message = f"Results truncated to first {params.head_limit} lines"
                output += f"\n... (results truncated to {params.head_limit} lines)"

        if not output:
            return format_success("", "No matches found")

        return format_success(output, message)

    except Exception as e:
        return format_error(f"Failed to grep. Error: {str(e)}")
