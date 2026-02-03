"""
read_file - Read text content from a file.

This tool reads text files with line numbers (like `cat -n` format),
supporting partial reads via offset and line limits.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_success

if TYPE_CHECKING:
    pass

MAX_LINES = 1000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 100 << 10  # 100KB
SNIFF_BYTES = 32  # Bytes to read for file type detection

# Magic bytes for common binary/media files
BINARY_SIGNATURES = [
    b"\x89PNG",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",  # GIF
    b"GIF89a",  # GIF
    b"RIFF",  # WEBP, AVI, WAV
    b"PK\x03\x04",  # ZIP, DOCX, XLSX, etc.
    b"PK\x05\x06",  # ZIP empty
    b"%PDF",  # PDF
    b"\x7fELF",  # ELF executable
    b"MZ",  # Windows executable
    b"\x00\x00\x00\x1c\x66\x74\x79\x70",  # MP4
    b"\x00\x00\x00\x20\x66\x74\x79\x70",  # MP4
]


def _is_binary_file(header: bytes) -> bool:
    """Check if a file appears to be binary based on magic bytes."""
    for sig in BINARY_SIGNATURES:
        if header.startswith(sig):
            return True
    # Also check for null bytes in the header (common in binary files)
    return b"\x00" in header


class ReadFileParams(BaseModel):
    """Parameters for read_file tool."""

    path: str = Field(
        description=(
            "The path to the file to read. Absolute paths are required when reading files "
            "outside the working directory."
        )
    )
    line_offset: int = Field(
        description=(
            "The line number to start reading from. "
            "By default read from the beginning of the file. "
            "Set this when the file is too large to read at once."
        ),
        default=1,
        ge=1,
    )
    n_lines: int = Field(
        description=(
            f"The number of lines to read. "
            f"By default read up to {MAX_LINES} lines, which is the max allowed value. "
            "Set this value when the file is too large to read at once."
        ),
        default=MAX_LINES,
        ge=1,
    )


def _truncate_line(line: str, max_length: int) -> str:
    """Truncate a line if it exceeds max_length."""
    if len(line) <= max_length:
        return line
    return line[: max_length - 3] + "..."


def _resolve_path(path_str: str, work_dir: Path) -> tuple[Path, str | None]:
    """
    Resolve and validate a file path.

    Returns:
        Tuple of (resolved_path, error_message). error_message is None if valid.
    """
    try:
        p = Path(path_str).expanduser()

        # Handle relative paths
        if not p.is_absolute():
            p = work_dir / p

        p = p.resolve()

        # Check if outside work_dir requires absolute path
        try:
            p.relative_to(work_dir)
        except ValueError:
            # Outside work_dir - original path must be absolute
            if not Path(path_str).expanduser().is_absolute():
                return p, (
                    f"`{path_str}` is not an absolute path. "
                    "You must provide an absolute path to read a file "
                    "outside the working directory."
                )

        return p, None
    except Exception as e:
        return Path(path_str), f"Invalid path: {e}"


@function_tool
async def read_file(
    ctx: RunContextWrapper[KimiToolContext], params: ReadFileParams
) -> str:
    """
    Read text content from a file.

    Tips:
    - Content will be returned with line numbers before each line (like `cat -n` format).
    - Use `line_offset` and `n_lines` parameters when you only need to read part of the file.
    - The maximum number of lines that can be read at once is 1000.
    - Any lines longer than 2000 characters will be truncated.
    - This tool can only read text files. For images/videos, use read_media_file.
    - If you want to search for content/pattern, prefer the grep tool over read_file.
    """
    work_dir = ctx.context.work_dir

    if not params.path:
        return format_error("File path cannot be empty.")

    # Resolve path
    p, error = _resolve_path(params.path, work_dir)
    if error:
        return format_error(error)

    # Check existence
    if not p.exists():
        return format_error(f"`{params.path}` does not exist.")
    if not p.is_file():
        return format_error(f"`{params.path}` is not a file.")

    # Check file type
    try:
        with open(p, "rb") as f:
            header = f.read(SNIFF_BYTES)
        if _is_binary_file(header):
            return format_error(
                f"`{params.path}` appears to be a binary file. "
                "Use read_media_file for images/videos, or appropriate shell commands "
                "for other binary formats."
            )
    except Exception:
        pass  # Continue anyway if we can't read the header

    try:
        # Read file content
        lines: list[str] = []
        n_bytes = 0
        truncated_line_numbers: list[int] = []
        max_lines_reached = False
        max_bytes_reached = False
        current_line_no = 0

        with open(p, encoding="utf-8", errors="replace") as f:
            for line in f:
                current_line_no += 1
                if current_line_no < params.line_offset:
                    continue

                truncated = _truncate_line(line, MAX_LINE_LENGTH)
                if truncated != line:
                    truncated_line_numbers.append(current_line_no)
                lines.append(truncated)
                n_bytes += len(truncated.encode("utf-8"))

                if len(lines) >= params.n_lines:
                    break
                if len(lines) >= MAX_LINES:
                    max_lines_reached = True
                    break
                if n_bytes >= MAX_BYTES:
                    max_bytes_reached = True
                    break

        # Format output with line numbers like `cat -n`
        lines_with_no: list[str] = []
        for line_num, line in zip(
            range(params.line_offset, params.line_offset + len(lines)), lines, strict=True
        ):
            # Use 6-digit line number width, right-aligned, with tab separator
            lines_with_no.append(f"{line_num:6d}\t{line}")

        # Build message
        message = (
            f"{len(lines)} lines read from file starting from line {params.line_offset}."
            if len(lines) > 0
            else "No lines read from file."
        )
        if max_lines_reached:
            message += f" Max {MAX_LINES} lines reached."
        elif max_bytes_reached:
            message += f" Max {MAX_BYTES} bytes reached."
        elif len(lines) < params.n_lines:
            message += " End of file reached."
        if truncated_line_numbers:
            message += f" Lines {truncated_line_numbers} were truncated."

        return format_success("".join(lines_with_no), message)

    except Exception as e:
        return format_error(f"Failed to read {params.path}. Error: {e}")
