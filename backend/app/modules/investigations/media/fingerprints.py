"""Pure-Python DCT perceptual fingerprint over a safely decoded normalized image."""

from __future__ import annotations

import math
import subprocess

from app.modules.investigations.image_safety import ImageValidationError

ANALYZER_ID = "PERCEPTUAL_HASH"
ANALYZER_VERSION = "1"
CONFIG_DIGEST = "dct-32-low-8-gray-v1"
_SIZE = 32
_LOW = 8

_COSINES = tuple(
    tuple(math.cos((2 * sample + 1) * frequency * math.pi / (2 * _SIZE)) for sample in range(_SIZE))
    for frequency in range(_LOW)
)


def perceptual_hash(data: bytes) -> str:
    """Return a 64-bit pHash for an already M1-validated normalized image."""
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-i",
                "pipe:0",
                "-frames:v",
                "1",
                "-vf",
                "scale=32:32:flags=area,format=gray",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            input=data,
            capture_output=True,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ImageValidationError(
            "PERCEPTUAL_HASH_FAILED", "Perceptual fingerprint failed"
        ) from exc
    pixels = result.stdout
    if len(pixels) != _SIZE * _SIZE:
        raise ImageValidationError("PERCEPTUAL_HASH_FAILED", "Perceptual fingerprint failed")
    rows = [pixels[index : index + _SIZE] for index in range(0, len(pixels), _SIZE)]
    horizontal = [
        [sum(rows[y][x] * _COSINES[u][x] for x in range(_SIZE)) for u in range(_LOW)]
        for y in range(_SIZE)
    ]
    coefficients = [
        sum(horizontal[y][u] * _COSINES[v][y] for y in range(_SIZE))
        for v in range(_LOW)
        for u in range(_LOW)
    ]
    ordered = sorted(coefficients)
    median = (ordered[31] + ordered[32]) / 2
    value = 0
    for coefficient in coefficients:
        value = (value << 1) | int(coefficient > median)
    return f"{value:016x}"


def hamming_distance(first: str, second: str) -> int:
    if len(first) != 16 or len(second) != 16:
        raise ValueError("pHash values must be 64-bit hexadecimal strings")
    return (int(first, 16) ^ int(second, 16)).bit_count()
