"""Bounded EXIF and decoded-image metadata with explicit privacy classes."""

from __future__ import annotations

import json
import struct
import subprocess

from app.modules.investigations.image_safety import ImageValidationError

ANALYZER_ID = "FILE_METADATA"
ANALYZER_VERSION = "1"
CONFIG_DIGEST = "allowlist-v1"
MAX_EXIF_ENTRIES = 512
MAX_EXIF_VALUE_BYTES = 4096

_INTERNAL_TAGS = {
    0x010F: ("make", "Make"),
    0x0110: ("model", "Model"),
    0x0131: ("software", "Software"),
    0x9000: ("exif_version", "ExifVersion"),
    0xA434: ("lens_model", "LensModel"),
}
_SENSITIVE_TIMESTAMP_TAGS = {
    0x0132: "DateTime",
    0x9003: "DateTimeOriginal",
    0x9004: "DateTimeDigitized",
}
_SENSITIVE_PRESENCE_TAGS = {0xA420, 0xA431, 0xA435, 0x013B, 0x8298}
_TIFF_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _exif_payload(data: bytes) -> bytes | None:
    if data.startswith(b"\xff\xd8"):
        cursor = 2
        while cursor + 4 <= len(data):
            if data[cursor] != 0xFF:
                cursor += 1
                continue
            while cursor < len(data) and data[cursor] == 0xFF:
                cursor += 1
            if cursor >= len(data):
                break
            marker = data[cursor]
            cursor += 1
            if marker in {0xD9, 0xDA} or cursor + 2 > len(data):
                break
            length = int.from_bytes(data[cursor : cursor + 2], "big")
            if length < 2 or cursor + length > len(data):
                break
            payload = data[cursor + 2 : cursor + length]
            if marker == 0xE1 and payload.startswith(b"Exif\x00\x00"):
                return payload[6:]
            cursor += length
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        cursor = 8
        while cursor + 12 <= len(data):
            length = int.from_bytes(data[cursor : cursor + 4], "big")
            kind = data[cursor + 4 : cursor + 8]
            end = cursor + 12 + length
            if end > len(data):
                break
            if kind == b"eXIf":
                return data[cursor + 8 : cursor + 8 + length]
            cursor = end
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        cursor = 12
        while cursor + 8 <= len(data):
            kind = data[cursor : cursor + 4]
            length = int.from_bytes(data[cursor + 4 : cursor + 8], "little")
            end = cursor + 8 + length
            if end > len(data):
                break
            if kind == b"EXIF":
                payload = data[cursor + 8 : end]
                return payload[6:] if payload.startswith(b"Exif\x00\x00") else payload
            cursor = end + (length & 1)
    return None


def _read_ifd(tiff: bytes, offset: int, endian: str) -> list[tuple[int, int, bytes]]:
    if offset < 8 or offset + 2 > len(tiff):
        return []
    count = struct.unpack_from(endian + "H", tiff, offset)[0]
    if count > MAX_EXIF_ENTRIES or offset + 2 + count * 12 > len(tiff):
        return []
    entries: list[tuple[int, int, bytes]] = []
    for index in range(count):
        position = offset + 2 + index * 12
        tag, value_type, item_count = struct.unpack_from(endian + "HHI", tiff, position)
        unit_size = _TIFF_TYPE_SIZES.get(value_type)
        if unit_size is None:
            continue
        size = item_count * unit_size
        if size > MAX_EXIF_VALUE_BYTES:
            continue
        start = (
            position + 8 if size <= 4 else struct.unpack_from(endian + "I", tiff, position + 8)[0]
        )
        if start < 0 or start + size > len(tiff):
            continue
        entries.append((tag, value_type, tiff[start : start + size]))
    return entries


def _decode_ascii(value_type: int, value: bytes) -> str | None:
    if value_type not in {2, 7}:
        return None
    text = value.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
    return text[:128] or None


def _parse_exif(data: bytes) -> dict[str, object]:
    payload = _exif_payload(data)
    if not payload:
        return {
            "exif_present": False,
            "gps_present": False,
            "orientation_present": False,
            "internal": {},
            "sensitive": {"timestamps": [], "sensitive_tag_presence": []},
        }
    if payload.startswith(b"Exif\x00\x00"):
        payload = payload[6:]
    if len(payload) < 8 or payload[:2] not in {b"II", b"MM"}:
        raise ValueError("invalid EXIF TIFF header")
    endian = "<" if payload[:2] == b"II" else ">"
    if struct.unpack_from(endian + "H", payload, 2)[0] != 42:
        raise ValueError("unsupported EXIF TIFF version")
    root_offset = struct.unpack_from(endian + "I", payload, 4)[0]
    root_entries = _read_ifd(payload, root_offset, endian)
    exif_offset = next(
        (
            struct.unpack(endian + "I", value)[0]
            for tag, value_type, value in root_entries
            if tag == 0x8769 and value_type == 4 and len(value) == 4
        ),
        None,
    )
    orientation_present = any(tag == 0x0112 for tag, _, _ in root_entries)
    gps_offset = next(
        (
            struct.unpack(endian + "I", value)[0]
            for tag, value_type, value in root_entries
            if tag == 0x8825 and value_type == 4 and len(value) == 4
        ),
        None,
    )
    gps_present = False
    if gps_offset is not None and gps_offset >= 8 and gps_offset + 2 <= len(payload):
        gps_count = struct.unpack_from(endian + "H", payload, gps_offset)[0]
        gps_present = gps_count <= MAX_EXIF_ENTRIES and gps_offset + 2 + gps_count * 12 <= len(
            payload
        )
    entries = root_entries + (_read_ifd(payload, exif_offset, endian) if exif_offset else [])
    internal: dict[str, str] = {}
    timestamps: list[dict[str, str]] = []
    sensitive_presence: list[str] = []
    for tag, value_type, value in entries:
        if tag in _INTERNAL_TAGS:
            name, source = _INTERNAL_TAGS[tag]
            decoded = _decode_ascii(value_type, value)
            if decoded:
                internal[name] = decoded
                internal[f"{name}_source_tag"] = source
        elif tag in _SENSITIVE_TIMESTAMP_TAGS:
            decoded = _decode_ascii(value_type, value)
            if decoded:
                timestamps.append({"source_tag": _SENSITIVE_TIMESTAMP_TAGS[tag], "value": decoded})
        elif tag in _SENSITIVE_PRESENCE_TAGS:
            sensitive_presence.append(hex(tag))
    return {
        "exif_present": True,
        "gps_present": gps_present,
        "orientation_present": orientation_present,
        "internal": internal,
        "sensitive": {
            "timestamps": timestamps,
            "sensitive_tag_presence": sensitive_presence,
        },
    }


def extract_metadata(data: bytes) -> dict[str, object]:
    """Return allowlisted safe, internal, and sensitive observations for one image."""
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,pix_fmt,color_space,color_primaries,color_transfer,color_range",
                "-of",
                "json",
                "pipe:0",
            ],
            input=data,
            capture_output=True,
            check=True,
            timeout=10,
        )
        streams = json.loads(probe.stdout.decode("utf-8")).get("streams", [])
        stream = streams[0]
        exif = _parse_exif(data)
    except (
        OSError,
        subprocess.SubprocessError,
        UnicodeError,
        ValueError,
        KeyError,
        IndexError,
    ) as exc:
        raise ImageValidationError(
            "METADATA_EXTRACTION_FAILED", "Image metadata could not be extracted"
        ) from exc
    pixel_format = str(stream.get("pix_fmt", "unknown"))[:40]
    codec = str(stream.get("codec_name", "unknown")).casefold()
    safe = {
        "format": "jpeg" if codec == "mjpeg" else codec[:20],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "pixel_format": pixel_format,
        "color_space": str(stream.get("color_space", "unknown"))[:40],
        "color_primaries": str(stream.get("color_primaries", "unknown"))[:40],
        "color_transfer": str(stream.get("color_transfer", "unknown"))[:40],
        "color_range": str(stream.get("color_range", "unknown"))[:40],
        "alpha_present": "a" in pixel_format.casefold(),
        "orientation_present": bool(exif["orientation_present"]),
        "gps_present": bool(exif["gps_present"]),
    }
    return {
        "safe": safe,
        "internal": exif["internal"],
        "sensitive": exif["sensitive"],
        "exif_present": bool(exif["exif_present"]),
        "supported_exif_present": bool(
            exif["internal"]
            or exif["orientation_present"]
            or exif["gps_present"]
            or exif["sensitive"]["timestamps"]
        ),
    }
