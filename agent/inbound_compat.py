"""Normalize known Agent 365 activity entity types without changing authentication."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
CANONICAL_ENTITY_TYPES = {"productinfo": "ProductInfo"}


def normalize_known_entity_types(body: Any) -> Any:
    if not isinstance(body, dict) or not isinstance(body.get("entities"), list):
        return body
    changed = False
    normalized = []
    for entity in body["entities"]:
        entity_type = entity.get("type") if isinstance(entity, dict) else None
        canonical = (
            CANONICAL_ENTITY_TYPES.get(entity_type.casefold())
            if isinstance(entity_type, str)
            else None
        )
        if canonical and canonical != entity_type:
            normalized.append({**entity, "type": canonical})
            changed = True
        else:
            normalized.append(entity)
    return {**body, "entities": normalized} if changed else body


class NormalizedBodyRequest:
    """Delegate the original authenticated request, replacing only its JSON entity casing."""

    def __init__(self, request: Any) -> None:
        self._request = request

    async def json(self) -> Any:
        body = await self._request.json()
        normalized = normalize_known_entity_types(body)
        if normalized is not body:
            logger.info("Canonicalized inbound entity types to the pinned SDK literals")
        return normalized

    def __getattr__(self, name: str) -> Any:
        return getattr(self._request, name)
