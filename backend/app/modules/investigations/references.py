"""Short case references: AZ- followed by five characters, for example AZ-7KQ2F.

The characters are Crockford base 32 (digits and letters without I, L, O and U), so a
reference is easy to read aloud and type on a phone, and cannot spell common words.
That gives 33.5 million references; a new one is drawn at random and redrawn on the
rare clash. Typed references are forgiving: case, spaces, a missing "AZ-" prefix and
the look-alikes O, I and L are all accepted. Older references (AZ-YYMMDD-XXXXXX)
stay valid.
"""

import re
import secrets
from collections.abc import Callable

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LENGTH = 5
PREFIX = "AZ-"
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})
_LEGACY = re.compile(r"AZ-?(\d{6})-?([A-F0-9]{6})")
_SHORT = re.compile(rf"(?:AZ)?([{ALPHABET}]{{{LENGTH}}})")
# Matches a reference inside a message, for commands such as "result AZ-7KQ2F".
PATTERN = r"(?:AZ[- ]?)?[0-9A-Za-z]{5}|AZ-?\d{6}-?[A-Fa-f0-9]{6}"


def new_reference(taken: Callable[[str], bool], *, attempts: int = 8) -> str:
    """Draw a random reference that `taken` reports as unused."""
    for _ in range(attempts):
        reference = PREFIX + "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
        if not taken(reference):
            return reference
    raise RuntimeError("Could not allocate a unique case reference")


def parse_reference(text: str | None) -> str | None:
    """The stored form of a typed reference, or None if it is not one."""
    compact = re.sub(r"[\s\-_#]", "", (text or "").upper())
    if not compact:
        return None
    legacy = _LEGACY.fullmatch(compact) or _LEGACY.fullmatch((text or "").strip().upper())
    if legacy:
        return f"AZ-{legacy.group(1)}-{legacy.group(2)}"
    body = compact[2:] if compact.startswith("AZ") and len(compact) == LENGTH + 2 else compact
    body = body.translate(_LOOKALIKES)
    match = _SHORT.fullmatch(body)
    return PREFIX + match.group(1) if match else None
