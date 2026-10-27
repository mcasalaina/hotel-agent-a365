#!/usr/bin/env python3
"""Verify Search and Foundry IQ before deploying the Hosted Agent."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, cast

from azure.identity import AzureCliCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import SearchIndexKnowledgeSource
from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
from azure.search.documents.knowledgebases.models import KnowledgeBaseRetrievalRequest
from azure.search.documents.models import VectorizableTextQuery
from foundry_iq_common import select_search_credential
from setup_foundry_iq import (
    INDEXES,
    KNOWLEDGE_BASE_NAME,
    SEMANTIC_CONFIGURATION_NAME,
)

SHARED_PROPERTY_ID = "chain-wide"


@dataclass(slots=True)
class VerificationReport:
    index_counts: dict[str, int] = field(default_factory=dict)
    index_modes: dict[str, str] = field(default_factory=dict)
    direct_queries: dict[str, int] = field(default_factory=dict)
    knowledge_sources: list[str] = field(default_factory=list)
    answer: str = ""
    reference_count: int = 0


def _knowledge_source_names() -> set[str]:
    return {f"{name.removesuffix('-index')}-ks" for name in INDEXES.values()}


def verify_knowledge_base(index_client: SearchIndexClient, knowledge_base_name: str) -> list[str]:
    expected = _knowledge_source_names()
    for index_name in INDEXES.values():
        source_name = f"{index_name.removesuffix('-index')}-ks"
        source = cast(SearchIndexKnowledgeSource, index_client.get_knowledge_source(source_name))
        if source.search_index_parameters.search_index_name != index_name:
            raise RuntimeError(f"{source_name} does not reference expected index {index_name}")
    knowledge_base = index_client.get_knowledge_base(knowledge_base_name)
    actual = {source.name for source in knowledge_base.knowledge_sources}
    if actual != expected:
        raise RuntimeError(
            f"Knowledge base sources differ. Expected {sorted(expected)}, found {sorted(actual)}"
        )
    output_mode = knowledge_base.as_dict().get("outputMode")
    if output_mode != "answerSynthesis":
        raise RuntimeError(f"Knowledge base answer synthesis is not enabled: {output_mode!r}")
    return sorted(actual)


def verify_direct_searches(
    search_endpoint: str,
    credential: Any,
    property_id: str,
    *,
    index_client: SearchIndexClient | None = None,
) -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    queries = {
        "properties": "parking",
        "policies": "cancellation",
        "dining-local": "restaurant",
        "operations": "maintenance",
    }
    counts: dict[str, int] = {}
    modes: dict[str, str] = {}
    if index_client is None:
        index_client = SearchIndexClient(
            search_endpoint, credential, api_version="2026-05-01-preview"
        )
    for route, query in queries.items():
        index = index_client.get_index(INDEXES[route])
        vector_fields = [
            item.name
            for item in index.fields
            if item.name == "content_vector" or item.vector_search_dimensions is not None
        ]
        modes[route] = "vector_semantic" if vector_fields else "semantic_lexical"
        client = SearchClient(search_endpoint, INDEXES[route], credential)
        results = list(
            client.search(
                query,
                query_type="semantic",
                semantic_configuration_name=SEMANTIC_CONFIGURATION_NAME,
                select=["id", "property_id", "title", "valid_from", "valid_to"],
                top=3,
            )
        )
        if not results:
            raise RuntimeError(f"Representative direct Search query returned no results: {route}")
        counts[route] = len(results)
        if vector_fields:
            vector_results = list(
                client.search(
                    search_text=None,
                    vector_queries=[
                        VectorizableTextQuery(
                            text=query,
                            k_nearest_neighbors=3,
                            fields=",".join(vector_fields),
                        )
                    ],
                    select=["id", "property_id", "title"],
                    top=3,
                )
            )
            if not vector_results:
                raise RuntimeError(
                    f"Representative integrated vector query returned no results: {route}"
                )
            counts[f"{route}_vector"] = len(vector_results)

    property_results = list(
        SearchClient(search_endpoint, INDEXES["properties"], credential).search(
            "parking",
            filter=f"property_id eq '{property_id.replace("'", "''")}'",
            select=["id", "property_id"],
            top=10,
        )
    )
    if not property_results or any(
        result["property_id"] != property_id for result in property_results
    ):
        raise RuntimeError(f"Property isolation failed for {property_id}")
    return counts, {"properties": len(property_results)}, modes


def retrieve_answer(
    search_endpoint: str,
    credential: Any,
    knowledge_base_name: str,
    question: str,
    property_id: str,
    as_of: str,
) -> tuple[str, list[Any]]:
    date_filter = (
        f"valid_from le '{as_of}' and valid_to ge '{as_of}' and "
        f"(property_id eq '{property_id.replace("'", "''")}' "
        f"or property_id eq '{SHARED_PROPERTY_ID}' or property_id eq null)"
    )
    request = KnowledgeBaseRetrievalRequest(
        {
            "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
            "outputMode": "answerSynthesis",
            "knowledgeSourceParams": [
                {
                    "kind": "searchIndex",
                    "knowledgeSourceName": source_name,
                    "includeReferences": True,
                    "includeReferenceSourceData": True,
                    "filterAddOn": date_filter,
                }
                for source_name in sorted(_knowledge_source_names())
            ],
        }
    )
    client = KnowledgeBaseRetrievalClient(
        endpoint=search_endpoint,
        credential=credential,
        knowledge_base_name=knowledge_base_name,
        api_version="2026-05-01-preview",
    )
    response = client.retrieve(retrieval_request=request)
    answer = "\n".join(_message_text(message) for message in (response.response or [])).strip()
    references = list(response.references or [])
    if not answer or not references:
        raise RuntimeError(
            "Knowledge-base answer synthesis did not return answer text and references"
        )
    if "[ref_id:" not in answer:
        raise RuntimeError("Knowledge-base answer did not include inline citations")
    _verify_temporal_references(references, as_of)
    return answer, references


def count_indexes(search_endpoint: str, credential: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for route, index_name in INDEXES.items():
        count = SearchClient(search_endpoint, index_name, credential).get_document_count()
        if count <= 0:
            raise RuntimeError(f"{index_name} has no indexed chunks")
        counts[route] = count
    return counts


def _message_text(message: Any) -> str:
    return "\n".join(getattr(content, "text", "") for content in (message.content or []))


def _verify_temporal_references(references: Iterable[Any], as_of: str) -> None:
    for reference in references:
        source_data = getattr(reference, "source_data", None) or {}
        valid_from = source_data.get("valid_from")
        valid_to = source_data.get("valid_to")
        if valid_from and valid_to and not valid_from <= as_of <= valid_to:
            raise RuntimeError(
                "Temporal notice/reference outside requested validity window: "
                f"{valid_from} to {valid_to}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--search-endpoint",
        default=os.getenv("AZURE_SEARCH_ENDPOINT"),
    )
    parser.add_argument(
        "--knowledge-base-name",
        default=os.getenv("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME", KNOWLEDGE_BASE_NAME),
    )
    parser.add_argument("--property-id", default="HTL-001")
    parser.add_argument("--as-of", default="2026-04-10")
    parser.add_argument("--tenant-id", help="Use Azure CLI credentials scoped to this tenant.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.search_endpoint:
        raise RuntimeError(
            "AZURE_SEARCH_ENDPOINT or --search-endpoint is required for live verification."
        )
    credential = (
        AzureCliCredential(tenant_id=args.tenant_id)
        if args.tenant_id
        else select_search_credential()
    )
    index_client = SearchIndexClient(
        endpoint=args.search_endpoint,
        credential=credential,
        api_version="2026-05-01-preview",
    )
    report = VerificationReport()
    report.index_counts = count_indexes(args.search_endpoint, credential)
    report.knowledge_sources = verify_knowledge_base(index_client, args.knowledge_base_name)
    report.direct_queries, property_isolation, report.index_modes = verify_direct_searches(
        args.search_endpoint, credential, args.property_id, index_client=index_client
    )
    report.direct_queries.update(
        {f"{name}_isolation": count for name, count in property_isolation.items()}
    )
    report.answer, references = retrieve_answer(
        args.search_endpoint,
        credential,
        args.knowledge_base_name,
        f"What dated operational notice applies to {args.property_id} on {args.as_of}?",
        args.property_id,
        args.as_of,
    )
    report.reference_count = len(references)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
