"""Bounded local inspection for uploaded images and short video files."""

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.modules.investigations.image_safety import ImageValidationError, normalize_image


def inspect_media(
    *, data: bytes, media_type: str, mime_type: str
) -> tuple[dict[str, object], list[tuple[str, bytes]], list[str]]:
    limitations: list[str] = []
    if media_type == "IMAGE":
        try:
            image, details = normalize_image(data)
            limitations.append(
                "The normalized analysis copy has metadata stripped; separate metadata and "
                "C2PA analyzers report what they could establish."
            )
            return (
                {
                    "inspection": "metadata-stripped-analysis-copy",
                    "normalized_sha256": hashlib.sha256(image).hexdigest(),
                    "normalization": details,
                },
                [("image/png", image)],
                limitations,
            )
        except Exception as exc:
            raise ImageValidationError("DERIVATION_FAILED", "Image normalization failed") from exc

    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        return (
            {},
            [],
            ["FFmpeg tools are unavailable; video metadata and keyframes were not extracted."],
        )
    with tempfile.TemporaryDirectory(prefix="agent-zero-media-") as temp_dir:
        video_path = Path(temp_dir) / "submitted-video"
        video_path.write_bytes(data)
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration,format_name:stream=codec_type,codec_name,width,height",
                    "-of",
                    "json",
                    str(video_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            metadata = json.loads(result.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError):
            return {}, [], ["Video metadata extraction failed; the media content was not assessed."]

        try:
            duration = float(metadata.get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            duration = 0
        if duration > 90:
            return metadata, [], ["Video exceeds the 90-second keyframe inspection limit."]
        if duration <= 0:
            return metadata, [], ["Video duration is unavailable; keyframes were not extracted."]

        frames: list[tuple[str, bytes]] = []
        for ratio in (0.15, 0.4, 0.65, 0.9):
            timestamp = max(0.0, min(duration - 0.1, duration * ratio))
            try:
                frame = subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-ss",
                        f"{timestamp:.3f}",
                        "-i",
                        str(video_path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=1024:-1",
                        "-f",
                        "image2pipe",
                        "-vcodec",
                        "mjpeg",
                        "pipe:1",
                    ],
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                if frame.stdout:
                    frames.append(("image/jpeg", frame.stdout))
            except subprocess.SubprocessError:
                limitations.append(
                    f"Could not extract the video frame near {timestamp:.1f} seconds."
                )
        if not frames:
            limitations.append("No video keyframes could be extracted.")
        limitations.append("The video audio track was not transcribed or analyzed in this pass.")
        metadata["keyframe_count"] = len(frames)
        return metadata, frames, limitations
