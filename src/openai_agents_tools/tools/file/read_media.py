"""
read_media_file - Read media content (images/videos) from a file.

This tool reads image and video files and returns them in a format
that can be processed by multimodal models.
"""

from __future__ import annotations

import base64
import mimetypes
from io import BytesIO
from pathlib import Path

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel, Field

from ...context import KimiToolContext
from ...errors import format_error, format_success

MAX_MEDIA_MEGABYTES = 100

# Common media file extensions and their MIME types
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v"}


class ReadMediaFileParams(BaseModel):
    """Parameters for read_media_file tool."""

    path: str = Field(
        description=(
            "The path to the file to read. Absolute paths are required when reading files "
            "outside the working directory."
        )
    )


def _detect_media_type(path: Path, header: bytes) -> tuple[str, str] | None:
    """
    Detect the media type of a file.

    Returns:
        Tuple of (kind, mime_type) where kind is 'image' or 'video',
        or None if not a recognized media type.
    """
    suffix = path.suffix.lower()

    # Check by extension first
    if suffix in IMAGE_EXTENSIONS:
        mime_type = mimetypes.guess_type(str(path))[0] or "image/jpeg"
        return ("image", mime_type)

    if suffix in VIDEO_EXTENSIONS:
        mime_type = mimetypes.guess_type(str(path))[0] or "video/mp4"
        return ("video", mime_type)

    # Check by magic bytes
    if header.startswith(b"\x89PNG"):
        return ("image", "image/png")
    if header.startswith(b"\xff\xd8\xff"):
        return ("image", "image/jpeg")
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return ("image", "image/gif")
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ("image", "image/webp")
    if header[4:8] == b"ftyp":
        # MP4/MOV/M4V
        return ("video", "video/mp4")

    return None


def _to_data_url(mime_type: str, data: bytes) -> str:
    """Convert binary data to a data URL."""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_image_size(data: bytes) -> tuple[int, int] | None:
    """Extract image dimensions using PIL if available."""
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            return image.size
    except Exception:
        return None


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
async def read_media_file(
    ctx: RunContextWrapper[KimiToolContext], params: ReadMediaFileParams
) -> str:
    """
    Read media content (image or video) from a file.

    Tips:
    - This tool can only read image or video files.
    - For text files, use the read_file tool instead.
    - The maximum file size is 100MB.
    - The media content will be returned in a form that you can directly view and understand.
    - If you need to output coordinates, output relative coordinates first and
      compute absolute coordinates using the original image size.

    Note: The actual media data is returned as a base64 data URL. The model
    should be capable of processing multimodal input to understand the content.
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

    try:
        # Check file size
        file_size = p.stat().st_size
        if file_size == 0:
            return format_error(f"`{params.path}` is empty.")
        if file_size > (MAX_MEDIA_MEGABYTES << 20):
            return format_error(
                f"`{params.path}` is {file_size} bytes, which exceeds the max "
                f"{MAX_MEDIA_MEGABYTES}MB for media files."
            )

        # Read header for type detection
        with open(p, "rb") as f:
            header = f.read(32)

        # Detect media type
        media_info = _detect_media_type(p, header)
        if media_info is None:
            return format_error(
                f"`{params.path}` is not a recognized image or video file. "
                "Use read_file for text files or appropriate shell commands for other formats."
            )

        kind, mime_type = media_info

        # Read the full file
        with open(p, "rb") as f:
            data = f.read()

        # Create data URL
        data_url = _to_data_url(mime_type, data)

        # Build message
        size_hint = ""
        if kind == "image":
            image_size = _extract_image_size(data)
            if image_size:
                size_hint = f", original size {image_size[0]}x{image_size[1]}px"

        message = (
            f"Loaded {kind} file `{p}` ({mime_type}, {file_size} bytes{size_hint}). "
            "If you need to output coordinates, output relative coordinates first and "
            "compute absolute coordinates using the original image size."
        )

        # Return the data URL - the model should be able to process this
        # In practice, OpenAI models expect image URLs in message content,
        # so this might need special handling by the caller
        return format_success(
            f"[Media: {kind}]\nData URL: {data_url[:100]}...(truncated for display)",
            message,
        )

    except Exception as e:
        return format_error(f"Failed to read {params.path}. Error: {e}")
