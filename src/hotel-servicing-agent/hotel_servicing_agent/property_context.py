from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

_PROPERTY_ID = re.compile(r"\bHTL-\d{3}\b", re.IGNORECASE)


@dataclass
class _PropertyEvidence:
    caller_property_id: str | None
    observed_property_ids: set[str] = field(default_factory=set)
    fabric_query_attempted: bool = False


_property_evidence: ContextVar[_PropertyEvidence | None] = ContextVar(
    "property_evidence", default=None
)


@contextmanager
def fabric_property_context(caller_property_id: str | None = None) -> Iterator[None]:
    token = _property_evidence.set(_PropertyEvidence(caller_property_id))
    try:
        yield
    finally:
        _property_evidence.reset(token)


def record_fabric_query_attempt() -> None:
    evidence = _property_evidence.get()
    if evidence is not None:
        evidence.fabric_query_attempted = True


def record_fabric_property_ids(answer: str) -> None:
    evidence = _property_evidence.get()
    if evidence is not None:
        evidence.observed_property_ids.update(
            match.group().upper() for match in _PROPERTY_ID.finditer(answer)
        )


def require_fabric_property_id(property_id: str) -> None:
    evidence = _property_evidence.get()
    if evidence is None or property_id not in evidence.observed_property_ids:
        raise ValueError(
            "Cross-source reservation property lookup rejected: the identifier must appear in "
            "a successful Fabric tool result in the current request. A confirmation marker "
            "alone is not evidence."
        )


def require_knowledge_property_id(property_id: str | None) -> None:
    evidence = _property_evidence.get()
    if evidence is None or not evidence.fabric_query_attempted:
        return
    if property_id is not None and (
        property_id == evidence.caller_property_id or property_id in evidence.observed_property_ids
    ):
        return
    raise ValueError(
        "Cross-source property lookup rejected: after an operations lookup, scope knowledge "
        "to a property observed in its successful result or explicitly named by the caller. "
        "Knowledge search cannot identify a guest's hotel. Do not retry with a guessed hotel "
        "or identifier. If the reservation was not retrieved, say it could not be verified."
    )
