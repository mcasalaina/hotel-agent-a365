"""Inbound activity compatibility helpers for the Agent 365 bridge.

The Agent 365 email notification channel sends the ``productInfo`` entity with a
lowerCamelCase type. The pinned ``microsoft-agents-activity`` models only accept the
canonical ``ProductInfo`` literal, so ``Activity.model_validate`` raises before any route or
handler runs and the bridge answers HTTP 500. Later SDK releases canonicalize known entity
types themselves; this module keeps the pinned release working without touching
authentication or any unrelated entity.

This module has no SDK imports so it stays importable in any environment.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

CANONICAL_ENTITY_TYPES = {"productinfo": "ProductInfo"}


def _canonical_entity_type(entity: Any) -> str | None:
    if not isinstance(entity, dict):
        return None
    entity_type = entity.get("type")
    if not isinstance(entity_type, str):
        return None
    canonical = CANONICAL_ENTITY_TYPES.get(entity_type.casefold())
    if canonical is None or canonical == entity_type:
        return None
    return canonical


def normalize_known_entity_types(body: Any) -> Any:
    """Return ``body`` with known entity type names canonicalized.

    Only entities whose type matches a known name case-insensitively are rewritten. The input is
    never mutated, and the same object is returned when nothing needs to change.
    """
    if not isinstance(body, dict):
        return body
    entities = body.get("entities")
    if not isinstance(entities, list):
        return body

    changed = False
    normalized: list[Any] = []
    for entity in entities:
        canonical = _canonical_entity_type(entity)
        if canonical is None:
            normalized.append(entity)
            continue
        normalized.append({**entity, "type": canonical})
        changed = True
    if not changed:
        return body
    return {**body, "entities": normalized}


def _role(body: dict[str, Any], key: str) -> str:
    account = body.get(key)
    if isinstance(account, dict) and isinstance(account.get("role"), str):
        return account["role"]
    return "-"


def describe_inbound_shape(body: Any) -> str:
    """Summarize an inbound activity for logs without message content, names or addresses."""
    if not isinstance(body, dict):
        return f"body={type(body).__name__}"
    entities = body.get("entities")
    entity_types = (
        [str(entity.get("type")) for entity in entities if isinstance(entity, dict)]
        if isinstance(entities, list)
        else []
    )
    fields = (
        f"channelId={body.get('channelId')}",
        f"type={body.get('type')}",
        f"name={body.get('name') or '-'}",
        f"id={body.get('id') or '-'}",
        f"deliveryMode={body.get('deliveryMode') or '-'}",
        f"entities={','.join(entity_types) or '-'}",
        f"recipientRole={_role(body, 'recipient')}",
        f"fromRole={_role(body, 'from')}",
        f"hasText={bool(body.get('text'))}",
    )
    return " ".join(fields)


class NormalizedBodyRequest:
    """HTTP request wrapper whose ``json()`` returns the normalized activity body.

    Everything else (method, headers, claims identity, path parameters) is delegated to the
    wrapped request, so authentication is evaluated exactly as before.
    """

    def __init__(self, request: Any) -> None:
        self._request = request

    async def json(self) -> Any:
        body = await self._request.json()
        normalized = normalize_known_entity_types(body)
        logger.info("Inbound activity: %s", describe_inbound_shape(normalized))
        if normalized is not body:
            logger.info("Canonicalized inbound entity types to the pinned SDK literals")
        return normalized

    def __getattr__(self, name: str) -> Any:
        return getattr(self._request, name)
