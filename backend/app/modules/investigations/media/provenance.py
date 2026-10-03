"""Bounded, local-only C2PA inspection of original image bytes."""

from __future__ import annotations

import io
import json
import multiprocessing
import re
from importlib.metadata import version
from typing import Any
from uuid import UUID

ANALYZER_ID = "C2PA"
ANALYZER_VERSION = "1"
ANALYSIS_TIMEOUT_SECONDS = 10
MAX_MANIFEST_JSON_BYTES = 1_000_000
MAX_OBSERVATION_BYTES = 32_000
MAX_ACTIONS = 20
MAX_INGREDIENTS = 20
MAX_STRING_LENGTH = 160

_LIMITATIONS = [
    (
        "C2PA credentials describe provenance assertions and do not establish the factual "
        "truth of depicted content."
    ),
    "Remote manifest retrieval and OCSP checks are disabled; remote ingredients are not fetched.",
]
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_SAFE_TEXT = re.compile(r"^[^\x00-\x1f<>]{1,160}$")
_AI_SOURCE_TYPES = {
    "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia": (
        "GENERATIVE_AI_CREATION_DECLARED"
    ),
    "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia": (
        "GENERATIVE_AI_CONTRIBUTION_DECLARED"
    ),
}


def config_digest_input() -> str:
    """Version all policy that can affect analyzer output and cache identity."""
    return json.dumps(
        {
            "sdk": version("c2pa-python"),
            "remote_manifest_fetch": False,
            "ocsp_fetch": False,
            "max_manifest_json_bytes": MAX_MANIFEST_JSON_BYTES,
            "max_actions": MAX_ACTIONS,
            "max_ingredients": MAX_INGREDIENTS,
            "max_string_length": MAX_STRING_LENGTH,
            "timeout_seconds": ANALYSIS_TIMEOUT_SECONDS,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _safe_token(value: object) -> str | None:
    return value if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value) else None


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > MAX_STRING_LENGTH
        or not _SAFE_TEXT.fullmatch(candidate)
        or "@" in candidate
        or "://" in candidate
        or "/" in candidate
        or "\\" in candidate
    ):
        return None
    return candidate


def _manifest_observation(
    reader: Any,
    *,
    asset_id: UUID | str,
    max_manifest_bytes: int = MAX_MANIFEST_JSON_BYTES,
) -> dict[str, object]:
    raw_manifest = reader.json()
    if not isinstance(raw_manifest, str) or len(raw_manifest.encode("utf-8")) > max_manifest_bytes:
        return _observation(
            asset_id=asset_id,
            state="INDETERMINATE",
            manifest_present=True,
            limitations=[*_LIMITATIONS, "The C2PA manifest exceeded the local extraction bound."],
        )

    try:
        document = json.loads(raw_manifest)
    except (json.JSONDecodeError, TypeError):
        return _observation(
            asset_id=asset_id,
            state="INDETERMINATE",
            manifest_present=True,
            limitations=[*_LIMITATIONS, "The SDK returned an unreadable manifest summary."],
        )

    active_id = document.get("active_manifest") if isinstance(document, dict) else None
    manifests = document.get("manifests", {}) if isinstance(document, dict) else {}
    manifest = manifests.get(active_id, {}) if isinstance(manifests, dict) else {}
    if not isinstance(manifest, dict):
        manifest = {}

    library_state = reader.get_validation_state()
    library_state = library_state if library_state in {"Trusted", "Valid", "Invalid"} else None
    sdk_valid = bool(reader.is_valid)
    if sdk_valid and library_state in {"Trusted", "Valid"}:
        state = "VALID"
    elif not sdk_valid and library_state == "Invalid":
        state = "INVALID"
    else:
        state = "INDETERMINATE"

    action_items: list[dict[str, object]] = []
    ai_disclosures: list[str] = []
    actions_truncated = False
    assertions = manifest.get("assertions", [])
    if not isinstance(assertions, list):
        assertions = []
    for assertion in assertions:
        if not isinstance(assertion, dict) or assertion.get("label") not in {
            "c2pa.actions",
            "c2pa.actions.v2",
        }:
            continue
        data = assertion.get("data")
        actions = data.get("actions", []) if isinstance(data, dict) else []
        if not isinstance(actions, list):
            continue
        for action_data in actions:
            if len(action_items) >= MAX_ACTIONS:
                actions_truncated = True
                break
            if not isinstance(action_data, dict):
                continue
            action_name = _safe_token(action_data.get("action"))
            if action_name is None:
                action_name = "UNRECOGNIZED_ACTION"
            source_type = action_data.get("digitalSourceType")
            ai_declaration = (
                _AI_SOURCE_TYPES.get(source_type) if isinstance(source_type, str) else None
            )
            action_items.append(
                {
                    "action": action_name,
                    "digital_source_type": (
                        source_type.rsplit("/", 1)[-1]
                        if isinstance(source_type, str) and source_type in _AI_SOURCE_TYPES
                        else None
                    ),
                }
            )
            if ai_declaration and ai_declaration not in ai_disclosures:
                ai_disclosures.append(ai_declaration)

    ingredient_items = manifest.get("ingredients", [])
    if not isinstance(ingredient_items, list):
        ingredient_items = []
    ingredient_count = len(ingredient_items)
    ingredient_summary = min(ingredient_count, MAX_INGREDIENTS)
    ingredients_truncated = ingredient_count > MAX_INGREDIENTS

    generator = manifest.get("claim_generator_info", [])
    if isinstance(generator, dict):
        generator = [generator]
    generator_info = generator[0] if isinstance(generator, list) and generator else {}
    if not isinstance(generator_info, dict):
        generator_info = {}
    signature_info = manifest.get("signature_info", {})
    if not isinstance(signature_info, dict):
        signature_info = {}
    validation_codes = _validation_codes(reader.get_validation_results())

    return _observation(
        asset_id=asset_id,
        state=state,
        manifest_present=True,
        validation_state=library_state,
        signature_state="VALIDATED" if sdk_valid else "NOT_VALIDATED",
        signer_identity=_safe_text(signature_info.get("common_name")),
        generator_name=_safe_text(generator_info.get("name")),
        generator_version=_safe_token(generator_info.get("version")),
        actions=action_items,
        actions_truncated=actions_truncated,
        ai_disclosures=ai_disclosures,
        ingredient_count=ingredient_summary,
        ingredients_truncated=ingredients_truncated,
        validation_codes=validation_codes,
        limitations=_LIMITATIONS,
    )


def _validation_codes(results: object) -> list[str]:
    if not isinstance(results, dict):
        return []
    active = results.get("activeManifest")
    if not isinstance(active, dict):
        return []
    codes: list[str] = []
    for severity in ("failure", "informational"):
        entries = active.get(severity, [])
        if not isinstance(entries, list):
            continue
        for item in entries:
            code = _safe_token(item.get("code")) if isinstance(item, dict) else None
            if code and code not in codes:
                codes.append(code)
                if len(codes) >= MAX_ACTIONS:
                    return codes
    return codes


def _observation(
    *,
    asset_id: UUID | str,
    state: str,
    manifest_present: bool,
    validation_state: str | None = None,
    signature_state: str = "UNKNOWN",
    signer_identity: str | None = None,
    generator_name: str | None = None,
    generator_version: str | None = None,
    actions: list[dict[str, object]] | None = None,
    actions_truncated: bool = False,
    ai_disclosures: list[str] | None = None,
    ingredient_count: int = 0,
    ingredients_truncated: bool = False,
    validation_codes: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, object]:
    return {
        "analyzer_id": ANALYZER_ID,
        "analyzer_version": ANALYZER_VERSION,
        "asset_id": str(asset_id),
        "state": state,
        "manifest_present": manifest_present,
        "validation_state": validation_state,
        "signature_state": signature_state,
        "signer_identity": signer_identity,
        "generator": {"name": generator_name, "version": generator_version},
        "actions": (actions or [])[:MAX_ACTIONS],
        "actions_truncated": actions_truncated,
        "ai_disclosures": (ai_disclosures or [])[:MAX_ACTIONS],
        "ingredient_count": min(max(ingredient_count, 0), MAX_INGREDIENTS),
        "ingredients_truncated": ingredients_truncated,
        "validation_codes": (validation_codes or [])[:MAX_ACTIONS],
        "limitations": (limitations or _LIMITATIONS)[:5],
    }


def inspect_c2pa_bytes(
    data: bytes,
    mime_type: str,
    asset_id: UUID | str,
    *,
    trust_anchors: str | None = None,
) -> dict[str, object]:
    """Read an embedded C2PA manifest with remote access disabled."""
    from c2pa import C2paError, Context, Reader

    settings: dict[str, object] = {"verify": {"remote_manifest_fetch": False, "ocsp_fetch": False}}
    if trust_anchors:
        settings["trust"] = {"user_anchors": trust_anchors}
    with Context.from_dict(settings) as context:
        try:
            reader = Reader.try_create(mime_type, io.BytesIO(data), context=context)
        except C2paError.NotSupported:
            return _observation(
                asset_id=asset_id,
                state="UNSUPPORTED",
                manifest_present=False,
                limitations=[*_LIMITATIONS, "The local C2PA SDK does not support this asset."],
            )
        except C2paError as exc:
            state = (
                "INVALID"
                if isinstance(exc, (C2paError.Verify, C2paError.Signature, C2paError.Manifest))
                else "INDETERMINATE"
            )
            return _observation(
                asset_id=asset_id,
                state=state,
                manifest_present=state == "INVALID",
                limitations=[
                    *_LIMITATIONS,
                    "The local C2PA SDK could not fully inspect the manifest.",
                ],
            )
        if reader is None:
            return _observation(
                asset_id=asset_id,
                state="NOT_PRESENT",
                manifest_present=False,
                limitations=[
                    *_LIMITATIONS,
                    "No supported C2PA manifest was detected in the original uploaded image.",
                ],
            )
        try:
            return _manifest_observation(reader, asset_id=asset_id)
        finally:
            reader.close()


def _c2pa_worker(connection: Any, data: bytes, mime_type: str, asset_id: str) -> None:
    try:
        result = inspect_c2pa_bytes(data, mime_type, asset_id)
        payload = json.dumps(result, separators=(",", ":")).encode("utf-8")
        if len(payload) > MAX_OBSERVATION_BYTES:
            payload = json.dumps(
                _observation(
                    asset_id=asset_id,
                    state="INDETERMINATE",
                    manifest_present=True,
                    limitations=[
                        *_LIMITATIONS,
                        "The bounded provenance observation exceeded its output limit.",
                    ],
                ),
                separators=(",", ":"),
            ).encode("utf-8")
        connection.send_bytes(payload)
    except BaseException:
        payload = json.dumps(
            _observation(
                asset_id=asset_id,
                state="ERROR",
                manifest_present=False,
                limitations=[
                    *_LIMITATIONS,
                    "Local C2PA analysis failed; no authenticity conclusion was drawn.",
                ],
            ),
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            connection.send_bytes(payload)
        except (BrokenPipeError, OSError):
            pass
    finally:
        connection.close()


def inspect_c2pa_bounded(data: bytes, mime_type: str, asset_id: UUID | str) -> dict[str, object]:
    """Enforce a hard wall-clock bound around the native SDK parser."""
    process_context = multiprocessing.get_context("spawn")
    receiver, sender = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=_c2pa_worker,
        args=(sender, data, mime_type, str(asset_id)),
        daemon=True,
    )
    try:
        process.start()
    except (OSError, RuntimeError):
        receiver.close()
        sender.close()
        return _observation(
            asset_id=asset_id,
            state="ERROR",
            manifest_present=False,
            limitations=[
                *_LIMITATIONS,
                "Local C2PA analysis could not start its bounded worker.",
            ],
        )
    sender.close()
    try:
        if receiver.poll(ANALYSIS_TIMEOUT_SECONDS):
            payload = receiver.recv_bytes(MAX_OBSERVATION_BYTES)
            result = json.loads(payload)
            if isinstance(result, dict):
                return result
        else:
            process.terminate()
            process.join(timeout=1)
            return _observation(
                asset_id=asset_id,
                state="ERROR",
                manifest_present=False,
                limitations=[
                    *_LIMITATIONS,
                    "Local C2PA analysis exceeded the time limit.",
                ],
            )
        return _observation(
            asset_id=asset_id,
            state="ERROR",
            manifest_present=False,
            limitations=[
                *_LIMITATIONS,
                "Local C2PA analysis returned no bounded observation.",
            ],
        )
    except (OSError, EOFError, json.JSONDecodeError):
        return _observation(
            asset_id=asset_id,
            state="ERROR",
            manifest_present=False,
            limitations=[
                *_LIMITATIONS,
                "Local C2PA analysis failed; no authenticity conclusion was drawn.",
            ],
        )
    finally:
        receiver.close()
        if process.is_alive():
            process.join(timeout=0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=0.5)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        if not process.is_alive():
            process.close()


def public_provenance_summary(observation: dict[str, object]) -> dict[str, object]:
    """Return only bounded workspace-safe fields from the internal observation."""
    return {
        "status": observation.get("state"),
        "credentials_present": observation.get("manifest_present") is True,
        "validation_state": observation.get("validation_state"),
        "signature_state": observation.get("signature_state"),
        "signer_identity_available": bool(observation.get("signer_identity")),
        "actions": observation.get("actions", [])[:MAX_ACTIONS],
        "ai_disclosures": observation.get("ai_disclosures", [])[:MAX_ACTIONS],
        "ingredient_count": observation.get("ingredient_count", 0),
        "validation_codes": observation.get("validation_codes", [])[:MAX_ACTIONS],
        "limitations": observation.get("limitations", [])[:5],
    }
