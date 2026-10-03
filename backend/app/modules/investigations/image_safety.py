"""Bounded FFmpeg validation and deterministic normalization for raster images."""

import json
import shutil
import subprocess

SUPPORTED_FORMATS = {
    "jpeg": ("image/jpeg", "JPEG"),
    "png": ("image/png", "PNG"),
    "webp": ("image/webp", "WEBP"),
}


class ImageValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _run(command: list[str], data: bytes, *, text: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            command, input=data, capture_output=True, check=True, timeout=15, text=text
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ImageValidationError("IMAGE_DECODE_FAILED", "Image could not be decoded") from exc


def validate_image(data: bytes, declared_mime: str | None, max_pixels: int) -> dict[str, object]:
    if data.startswith(b"\xff\xd8\xff"):
        signature = "jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        signature = "png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        signature = "webp"
    else:
        raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "Unsupported image format")
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise ImageValidationError("IMAGE_DECODE_FAILED", "Image decoder is unavailable")
    probe = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            "pipe:0",
        ],
        data,
    )
    try:
        streams = json.loads(probe.stdout.decode("utf-8")).get("streams", [])
        if not streams:
            raise ValueError("missing image stream")
        stream = streams[0]
        codec = str(stream["codec_name"]).lower()
        codec = "jpeg" if codec == "mjpeg" else codec
        width, height = int(stream["width"]), int(stream["height"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ImageValidationError("IMAGE_DECODE_FAILED", "Image could not be decoded") from exc
    if codec not in SUPPORTED_FORMATS:
        raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "Unsupported image format")
    if codec != signature:
        raise ImageValidationError("INVALID_MEDIA", "Image signature does not match decoded format")
    if (
        width <= 0
        or height <= 0
        or width > max_pixels
        or height > max_pixels
        or width * height > max_pixels
    ):
        raise ImageValidationError("IMAGE_PIXEL_LIMIT_EXCEEDED", "Image dimensions exceed limits")
    expected_mime, actual_format = SUPPORTED_FORMATS[codec]
    if declared_mime and declared_mime not in {expected_mime, "application/octet-stream"}:
        raise ImageValidationError("INVALID_MEDIA", "Declared media type does not match image")
    _run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", "pipe:0", "-frames:v", "1", "-f", "null", "-"],
        data,
    )
    return {"format": actual_format, "mime_type": expected_mime, "width": width, "height": height}


def normalize_image(data: bytes) -> tuple[bytes, dict[str, object]]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-xerror",
        "-i",
        "pipe:0",
        "-frames:v",
        "1",
        "-map_metadata",
        "-1",
        "-vf",
        "scale=iw:ih",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    try:
        result = subprocess.run(command, input=data, capture_output=True, check=True, timeout=15)
    except (subprocess.SubprocessError, OSError) as exc:
        raise ImageValidationError("IMAGE_DECODE_FAILED", "Image normalization failed") from exc
    if not result.stdout:
        raise ImageValidationError("IMAGE_DECODE_FAILED", "Image normalization failed")
    try:
        version_result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True, text=True, timeout=5
        )
        tool_version = version_result.stdout.splitlines()[0]
    except (subprocess.SubprocessError, OSError, IndexError):
        tool_version = "unknown"
    return result.stdout, {
        "operation": "normalize_image",
        "tool": "ffmpeg",
        "tool_version": tool_version,
        "output_format": "PNG",
        "orientation": "FFmpeg autorotation applied when orientation metadata exists",
        "alpha": "preserved by PNG encoding when supported",
        "color": "FFmpeg decoder default conversion",
        "metadata": "not copied",
        "upscaled": False,
        "cropped": False,
    }
