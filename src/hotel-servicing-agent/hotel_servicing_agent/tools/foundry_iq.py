from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent_framework import FunctionTool
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import KnowledgeBaseRetrievalRequest

KNOWLEDGE_SOURCE_NAMES = (
    "hotel-properties-ks",
    "hotel-policies-ks",
    "hotel-dining-local-ks",
    "hotel-operations-ks",
)
SHARED_PROPERTY_ID = "chain-wide"


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
                "Returns a concise cited answer. Supply property_id and as_of when known."
            ),
            func=self.search,
        )

    def search(
        self,
        question: str,
        property_id: str | None = None,
        as_of: str | None = None,
    ) -> str:
        if not question.strip():
            raise ValueError("question must not be empty")
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
        return json.dumps(_serialize_response(response), ensure_ascii=False, separators=(",", ":"))


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
