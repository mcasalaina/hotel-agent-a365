from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"(?:authorization|access.?token|refresh.?token|client.?secret|"
    r"assertion|password|credential|cookie)",
    re.IGNORECASE,
)
_CONTENT_KEY = re.compile(
    r"(?:gen_ai\.(?:input|output)\.messages|message\.content|tool\.(?:result|output)|"
    r"mail(?:box)?\.content|chat\.content)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*\b")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def redact_string(value: str) -> str:
    value = _BEARER.sub("[REDACTED_BEARER_TOKEN]", value)
    value = _JWT.sub("[REDACTED_JWT]", value)
    return _EMAIL.sub("[REDACTED_EMAIL]", value)


def redact(value: Any, *, include_content: bool = False) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_string = str(key)
            if _SENSITIVE_KEY.search(key_string):
                result[key_string] = "[REDACTED_SECRET]"
            elif not include_content and _CONTENT_KEY.search(key_string):
                result[key_string] = "[REDACTED_CONTENT]"
            else:
                result[key_string] = redact(item, include_content=include_content)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item, include_content=include_content) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value
