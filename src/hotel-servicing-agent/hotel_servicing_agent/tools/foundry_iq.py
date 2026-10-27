from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from agent_framework import FunctionTool
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import KnowledgeBaseRetrievalRequest

from hotel_servicing_agent.language import LANGUAGE_RESPONSE_GUIDANCE
from hotel_servicing_agent.property_catalog import (
    PROPERTY_NAMES,
    PropertyId,
    official_property_name,
)
from hotel_servicing_agent.property_catalog import (
    property_id_from_text as _property_id_from_question,
)
from hotel_servicing_agent.property_context import (
    require_fabric_property_id,
    require_knowledge_property_id,
)

KNOWLEDGE_SOURCE_NAMES = (
    "hotel-properties-ks",
    "hotel-policies-ks",
    "hotel-dining-local-ks",
    "hotel-operations-ks",
)
SHARED_PROPERTY_ID = "chain-wide"
PROPERTY_INDEX_NAME = "hotel-properties-index"
_FABRIC_PROPERTY_CONFIRMATION = re.compile(
    r"\bconfirmed\s+from\s+fabric\s*:\s*(HTL-\d{3})\b",
    re.IGNORECASE,
)
_CITATION_RESPONSE_GUIDANCE = (
    "When the user asks for a source or citation, the final answer must name the actual "
    "references[].title and its references[].valid_from effective date. "
    "Quoting a policy sentence is not a substitute for naming its source. "
    "Preserve the official document title verbatim as a proper name; translate the surrounding "
    "source label and explanation into the user's response language."
)


class FoundryIQTool:
    """Retrieves citation-backed hotel knowledge through the managed knowledge base."""

    def __init__(
        self,
        search_endpoint: str,
        knowledge_base_name: str,
        credential: Any,
        client_factory: Callable[..., Any] = KnowledgeBaseRetrievalClient,
        search_client_factory: Callable[..., Any] = SearchClient,
    ) -> None:
        self._search_endpoint = search_endpoint
        self._knowledge_base_name = knowledge_base_name
        self._credential = credential
        self._client_factory = client_factory
        self._search_client_factory = search_client_factory

    def as_function_tool(self) -> FunctionTool:
        property_roster = "; ".join(
            f"{name} = {property_id}" for property_id, name in PROPERTY_NAMES.items()
        )
        return FunctionTool(
            name="search_hotel_knowledge",
            description=(
                "Search approved hotel property, policy, dining, and operations knowledge. "
                "Returns a concise cited answer. Preserve the user's property name, city, or "
                "identifier verbatim in question. Never guess property_id. Use the canonical "
                "roster below or omit property_id when it is unknown; this tool resolves named "
                "hotels directly, without an operations-data lookup. Supply as_of when known. "
                "Always "
                "supply property_id for a follow-up about an established hotel, even when the user "
                "omits its name. For a cross-source reservation lookup, first obtain property_id "
                "from Fabric and include 'Confirmed from Fabric: HTL-###' in the question. "
                f"Canonical internal property roster: {property_roster}."
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
        named_property_id = _property_id_from_question(question)
        normalized_question = question.casefold()
        if (
            property_id
            and named_property_id
            and "reservation" in normalized_question
            and "property" in normalized_question
        ):
            _validate_cross_source_property_context(question, property_id)
        effective_property_id = named_property_id or property_id
        _validate_cross_source_property_context(question, effective_property_id)
        require_knowledge_property_id(effective_property_id)
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
                        "filterAddOn": _filter_for(effective_property_id, effective_date),
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
        try:
            response = client.retrieve(retrieval_request=request)
            result = _serialize_response(response)
        except HttpResponseError:
            if not effective_property_id:
                raise
            result = {"answer": "", "references": []}
        if effective_property_id and not _has_property_reference(result, effective_property_id):
            direct_result = self._retrieve_property_profile(effective_property_id, effective_date)
            if direct_result:
                result = direct_result
        if effective_property_id:
            result["property"] = {
                "property_id": effective_property_id,
                "official_name": official_property_name(effective_property_id),
            }
        result["response_guidance"] = f"{LANGUAGE_RESPONSE_GUIDANCE} {_CITATION_RESPONSE_GUIDANCE}"
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    def _retrieve_property_profile(
        self,
        property_id: PropertyId,
        as_of: str,
    ) -> dict[str, object] | None:
        client = self._search_client_factory(
            endpoint=self._search_endpoint,
            index_name=PROPERTY_INDEX_NAME,
            credential=self._credential,
        )
        rows = list(
            client.search(
                search_text="*",
                filter=(
                    f"property_id eq '{property_id}' and "
                    f"valid_from le '{as_of}' and valid_to ge '{as_of}'"
                ),
                select=[
                    "id",
                    "document_id",
                    "title",
                    "property_id",
                    "valid_from",
                    "valid_to",
                    "source_path",
                    "content",
                ],
                top=1,
            )
        )
        if not rows:
            return None
        row = rows[0]
        return {
            "answer": f"{str(row['content']).strip()} [ref_id:0]",
            "references": [
                {
                    "id": row["id"],
                    "document_id": row["document_id"],
                    "source_path": row["source_path"],
                    "title": row["title"],
                    "property_id": row["property_id"],
                    "valid_from": row["valid_from"],
                    "valid_to": row["valid_to"],
                }
            ],
        }


def _has_property_reference(result: dict[str, object], property_id: PropertyId) -> bool:
    references = result.get("references")
    return isinstance(references, list) and any(
        isinstance(reference, dict) and reference.get("property_id") == property_id
        for reference in references
    )


def _validate_cross_source_property_context(
    question: str,
    property_id: PropertyId | None,
) -> None:
    normalized = question.casefold()
    match = _FABRIC_PROPERTY_CONFIRMATION.search(question)
    if match is None and ("reservation" not in normalized or "property" not in normalized):
        return
    if match is None:
        raise ValueError(
            "Cross-source reservation property lookup rejected: first wait for the Fabric result, "
            "then retry with the exact marker 'Confirmed from Fabric: HTL-###'."
        )
    confirmed_property_id = match.group(1).upper()
    if property_id is None or property_id != confirmed_property_id:
        raise ValueError(
            "Cross-source reservation property lookup rejected: property_id must exactly match "
            f"the Fabric-confirmed identifier {confirmed_property_id}."
        )
    require_fabric_property_id(property_id)


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
