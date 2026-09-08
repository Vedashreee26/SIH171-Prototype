"""
Local PII detection and redaction.

This module must run on-device. It never calls a network API and never
writes original sensitive values to disk. Callers (vision / Flask routes)
should send ONLY the returned structure to the server.

Public API:
    redact_sensitive_data(data) -> JSON-compatible copy with PII replaced.
"""

from __future__ import annotations

import copy
import re
from typing import Any

# Placeholders stay visible so the agent can still see *what kind* of field
# this was, without seeing the raw value.
REDACTED_EMAIL = "[REDACTED_EMAIL]"
REDACTED_PHONE = "[REDACTED_PHONE]"
REDACTED_PASSWORD = "[REDACTED_PASSWORD]"
REDACTED_CARD = "[REDACTED_CARD]"
REDACTED_ID = "[REDACTED_ID]"
REDACTED_PII = "[REDACTED_PII]"

# UI keys we keep as structure. Values under these keys are still scanned
# for inline PII (e.g. an email accidentally used as a label), but we never
# wipe the whole key just because the field nearby is a password.
# Labels/types describe the control to the agent; keep them unless they
# themselves contain an inline email/phone/card.
STRUCTURAL_KEYS = {
    "type",
    "input_type",
    "label",
    "role",
    "tag",
    "action",
    "direction",
    "bbox",
    "x",
    "y",
    "width",
    "height",
    "top",
    "left",
    "right",
    "bottom",
}

PASSWORD_KEY_HINTS = (
    "password",
    "passwd",
    "passcode",
    "pwd",
    "secret",
    "pin",
)

NAME_KEY_HINTS = (
    "full_name",
    "fullname",
    "first_name",
    "last_name",
    "given_name",
    "family_name",
    "surname",
    "display_name",
    "legal_name",
)

# High-precision-ish patterns. Order matters: more specific first.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)
# US SSN-like: 123-45-6789 (not 000, 666, 9xx area in the wild — keep simple).
_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
# Indian PAN: ABCDE1234F
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
# Aadhaar-like groups: 1234 5678 9012 (not the first 12 digits of a card).
_AADHAAR_GROUPED_RE = re.compile(r"\b[2-9]\d{3}\s\d{4}\s\d{4}(?!\s?\d)\b")
# Card-like groups (spaces or dashes). Luhn is applied after match.
_CARD_GROUPED_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
# Phone: require a +country code OR separators so we skip plain years/IDs.
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s\-]?)?(?:\(?\d{2,4}\)?[\s.\-]?)?\d{3}[\s.\-]?\d{4}(?!\w)"
)
# Indian 10-digit mobiles starting 6-9, optional +91.
_IN_MOBILE_RE = re.compile(r"(?<!\d)(?:\+91[\s\-]?)?[6-9]\d{9}(?!\d)")

# Person-name heuristic: 2–4 Capitalized tokens, letters/'/- only.
_NAME_VALUE_RE = re.compile(
    r"^[A-Z][a-z]+(?:[ '\-][A-Z][a-z]+){1,3}$"
)


def redact_sensitive_data(data: Any) -> Any:
    """
    Return a JSON-compatible copy of `data` with obvious PII replaced.

    Accepts nested dicts/lists (typical vision output: {"elements": [...]}),
    and also a bare string. Unknown types are converted with str() only when
    they are not JSON-safe primitives.
    """
    # Work on a deep copy so the caller still holds the original locally
    # and we never mutate it in place.
    cloned = copy.deepcopy(data)
    return _walk(cloned, field_hints=())


def _walk(node: Any, field_hints: tuple[str, ...]) -> Any:
    if node is None or isinstance(node, bool):
        return node
    if isinstance(node, (int, float)):
        return _redact_number(node, field_hints)
    if isinstance(node, str):
        return _redact_string(node, field_hints)
    if isinstance(node, list):
        return [_walk(item, field_hints) for item in node]
    if isinstance(node, tuple):
        return [_walk(item, field_hints) for item in node]
    if isinstance(node, dict):
        hints_here = field_hints + _hints_from_element(node)
        out = {}
        for key, value in node.items():
            key_s = str(key)
            child_hints = hints_here + (key_s.lower(),)
            if key_s.lower() in STRUCTURAL_KEYS and not isinstance(value, (dict, list)):
                # Keep layout/type, but still strip inline emails/phones if any.
                if isinstance(value, str):
                    out[key] = _redact_inline_patterns(value)
                else:
                    out[key] = value
            else:
                out[key] = _walk(value, child_hints)
        return out
    # Non-JSON leftovers: stringify then redact so the result stays serializable.
    return _redact_string(str(node), field_hints)


def _hints_from_element(element: dict) -> tuple[str, ...]:
    """Collect label/type/name so password and name fields redact whole values."""
    parts = []
    for key in ("type", "input_type", "label", "name", "placeholder", "autocomplete", "id"):
        val = element.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.lower())
    return tuple(parts)


def _is_password_field(hints: tuple[str, ...]) -> bool:
    blob = " ".join(hints)
    if "type=password" in blob:
        return True
    # "password" as the element type from vision, or in the field name.
    tokens = re.split(r"[^a-z0-9]+", blob)
    if "password" in tokens or any(h in PASSWORD_KEY_HINTS for h in tokens):
        return True
    return any(h in blob for h in PASSWORD_KEY_HINTS)


def _is_name_field(hints: tuple[str, ...]) -> bool:
    blob = " ".join(hints)
    tokens = set(re.split(r"[^a-z0-9]+", blob))
    if "name" in tokens and "username" not in tokens:
        return True
    return any(h.replace("_", " ") in blob or h in tokens for h in NAME_KEY_HINTS)


def _redact_number(value: int | float, hints: tuple[str, ...]) -> Any:
    if _is_password_field(hints):
        return REDACTED_PASSWORD
    digits = re.sub(r"\D", "", str(value))
    if _looks_like_card(digits):
        return REDACTED_CARD
    return value


def _redact_string(value: str, hints: tuple[str, ...]) -> str:
    if value == "":
        return value
    if _is_password_field(hints):
        return REDACTED_PASSWORD
    if _is_name_field(hints) and _looks_like_person_name(value.strip()):
        return REDACTED_PII
    return _redact_inline_patterns(value)


def _redact_inline_patterns(text: str) -> str:
    """Replace obvious PII substrings; leave surrounding UI copy intact."""
    if not text:
        return text

    text = _EMAIL_RE.sub(REDACTED_EMAIL, text)
    text = _PAN_RE.sub(REDACTED_ID, text)
    text = _SSN_RE.sub(REDACTED_ID, text)

    def _card_sub(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if _looks_like_card(digits):
            return REDACTED_CARD
        return match.group(0)

    # Cards before Aadhaar so a 16-digit grouped number is not sliced as an ID.
    text = _CARD_GROUPED_RE.sub(_card_sub, text)
    text = _AADHAAR_GROUPED_RE.sub(REDACTED_ID, text)
    text = _IN_MOBILE_RE.sub(REDACTED_PHONE, text)
    text = _PHONE_RE.sub(REDACTED_PHONE, text)
    return text


def _looks_like_person_name(value: str) -> bool:
    if not value or "@" in value:
        return False
    # Avoid treating button labels like "Submit Form" as names: require 2+ words.
    return bool(_NAME_VALUE_RE.match(value))


def _looks_like_card(digits: str) -> bool:
    """13–19 digits passing Luhn — cuts false positives vs random numbers."""
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    # Skip obvious test runs of one digit.
    if len(set(digits)) == 1:
        return False
    return _luhn_ok(digits)


def _luhn_ok(digits: str) -> bool:
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = ord(ch) - 48
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0
