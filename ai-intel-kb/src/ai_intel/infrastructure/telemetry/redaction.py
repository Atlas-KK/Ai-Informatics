"""Defense-in-depth removal of credentials from local diagnostics."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?i)(authorization|proxy-authorization|api[_-]?key|token|cookie|secret|credential)"
)
_AUTHORIZATION_VALUE = re.compile(r"(?im)\b(proxy-authorization|authorization)\s*[:=]\s*[^\r\n]*")
_INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|cookie|secret|credential)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)


def redact_text(value: str) -> str:
    without_auth = _AUTHORIZATION_VALUE.sub(lambda match: f"{match.group(1)}={REDACTED}", value)
    return _INLINE_SECRET.sub(lambda match: f"{match.group(1)}={REDACTED}", without_auth)


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_value(item, key=str(item_key)) for item_key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [redact_value(item) for item in value]
    return value
