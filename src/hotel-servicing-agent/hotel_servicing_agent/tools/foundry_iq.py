from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent_framework import FunctionTool
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import KnowledgeBaseRetrievalRequest

from hotel_servicing_agent.property_catalog import PropertyId, official_property_name

KNOWLEDGE_SOURCE_NAMES = (
    "hotel-properties-ks",
    "hotel-policies-ks",
    "hotel-dining-local-ks",
    "hotel-operations-ks",
)
SHARED_PROPERTY_ID = "chain-wide"
_FABRIC_PROPERTY_CONFIRMATION = re.compile(
    r"\bconfirmed\s+from\s+fabric\s*:\s*(HTL-\d{3})\b",
    re.IGNORECASE,
)


class FoundryIQTool:
    """Retrieves citation-backed hotel knowledge through the managed knowledge base."""

    def __init__(
        self,
        search_endpoint: str,
        knowledge_base_name: str,
        credential: Any,
        client_factory: Callable[..., Any] = KnowledgeBaseRetrievalClient,
    ) -> None:
        self._search_endpoint = search_endpoint
        self._knowledge_base_name = knowledge_base_name
        self._credential = credential
        self._client_factory = client_factory

    def as_function_tool(self) -> FunctionTool:
        return FunctionTool(
            name="search_hotel_knowledge",
            description=(
                "Search approved hotel property, policy, dining, and operations knowledge. "
                "Returns a concise cited answer. Supply property_id and as_of when known. For a "
                "cross-source reservation lookup, first obtain property_id from Fabric and include "
                "'Confirmed from Fabric: HTL-###' in the question."
            ),
            func=self.search,
        )

    def search(
        self,
        question: str,
        property_id: PropertyId | None = None,
        as_of: str | None = None,
    ) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
        _validate_cross_source_property_context(question, property_id)
        effective_date = as_of or datetime.now(UTC).date().isoformat()
        request = KnowledgeBaseRetrievalRequest(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": question.strip()}],
                    }
                ],
                "outputMode": "answerSynthesis",
                "knowledgeSourceParams": [
                    {
                        "kind": "searchIndex",
                        "knowledgeSourceName": source_name,
                        "includeReferences": True,
                        "includeReferenceSourceData": True,
                        "filterAddOn": _filter_for(property_id, effective_date),
                    }
                    for source_name in KNOWLEDGE_SOURCE_NAMES
                ],
            }
        )
        client = self._client_factory(
            endpoint=self._search_endpoint,
            credential=self._credential,
            knowledge_base_name=self._knowledge_base_name,
            api_version="2026-05-01-preview",
        )
        response = client.retrieve(retrieval_request=request)
        result = _serialize_response(response)
        if property_id:
            result["property"] = {
                "property_id": property_id,
                "official_name": official_property_name(property_id),
            }
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _validate_cross_source_property_context(
    question: str,
    property_id: PropertyId | None,
) -> None:
    normalized = question.casefold()
    if "reservation" not in normalized or "property" not in normalized:
        return
    match = _FABRIC_PROPERTY_CONFIRMATION.search(question)
    if match is None:
        raise ValueError(
            "Cross-source reservation property lookup rejected: first wait for the Fabric result, "
            "then retry with the exact marker 'Confirmed from Fabric: HTL-###'."
        )
    confirmed_property_id = match.group(1).upper()
    if property_id != confirmed_property_id:
        raise ValueError(
            "Cross-source reservation property lookup rejected: property_id must exactly match "
            f"the Fabric-confirmed identifier {confirmed_property_id}."
        )


def _filter_for(property_id: str | None, as_of: str) -> str:
    date_clause = f"valid_from le '{as_of}' and valid_to ge '{as_of}'"
    if not property_id:
        return date_clause
    escaped_property_id = property_id.replace("'", "''")
    return (
        f"({date_clause}) and (property_id eq '{escaped_property_id}' "
        f"or property_id eq '{SHARED_PROPERTY_ID}' or property_id eq null)"
    )


def _serialize_response(response: Any) -> dict[str, object]:
    messages = getattr(response, "response", None) or []
    response_references = getattr(response, "references", None) or []
    answer = "\n".join(_message_text(message) for message in messages)
    references = [_reference(reference) for reference in response_references]
    return {"answer": answer.strip(), "references": references}


def _message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content", [])
    return "\n".join(
        str(item.get("text", "")) if isinstance(item, dict) else str(getattr(item, "text", ""))
        for item in (content or [])
    ).strip()


def _reference(reference: Any) -> dict[str, object]:
    source_data = getattr(reference, "source_data", None)
    if source_data is None and isinstance(reference, dict):
        source_data = reference.get("sourceData", reference.get("source_data"))
    return {
        "id": _value(reference, "id"),
        "document_id": _value(reference, "doc_key", "docKey"),
        "source_path": (
            (source_data or {}).get("source_path") if isinstance(source_data, dict) else None
        ),
        "title": (source_data or {}).get("title") if isinstance(source_data, dict) else None,
        "property_id": (
            (source_data or {}).get("property_id") if isinstance(source_data, dict) else None
        ),
        "valid_from": (
            (source_data or {}).get("valid_from") if isinstance(source_data, dict) else None
        ),
        "valid_to": (
            (source_data or {}).get("valid_to") if isinstance(source_data, dict) else None
        ),
    }


def _value(value: Any, attribute: str, mapping_key: str | None = None) -> object:
    if isinstance(value, dict):
        return value.get(mapping_key or attribute)
    return getattr(value, attribute, None)
