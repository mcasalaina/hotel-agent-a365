#!/usr/bin/env python3
"""Create the repeatable Search and Foundry IQ knowledge-base configuration."""

from __future__ import annotations

import argparse
import hashlib
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    AzureOpenAIVectorizer,
    AzureOpenAIVectorizerParameters,
    HnswAlgorithmConfiguration,
    KnowledgeBase,
    SearchField,
    SearchIndex,
    SearchIndexFieldReference,
    SearchIndexKnowledgeSource,
    SearchIndexKnowledgeSourceParameters,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.storage.blob import BlobServiceClient
from foundry_iq_common import select_search_credential
from openai import AzureOpenAI

EMBEDDING_DEPLOYMENT = "text-embedding-3-small"
QUERY_PLANNING_DEPLOYMENT = "gpt-5.4-mini"
KNOWLEDGE_BASE_NAME = "hotel-foundryiq"
EMBEDDING_DIMENSIONS = 1536
SEMANTIC_CONFIGURATION_NAME = "hotel-semantic"
INDEXES = {
    "properties": "hotel-properties-index",
    "policies": "hotel-policies-index",
    "dining-local": "hotel-dining-local-index",
    "operations": "hotel-operations-index",
}


@dataclass(frozen=True, slots=True)
class CorpusDocument:
    document_id: str
    title: str
    property_id: str | None
    category: str
    valid_from: str
    valid_to: str
    locale: str
    source_path: str
    route: str
    content: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    document: CorpusDocument
    ordinal: int
    content: str


def parse_frontmatter(text: str, source: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError(f"{source}: missing YAML frontmatter")
    closing = text.find("\n---", 4)
    if closing < 0:
        raise ValueError(f"{source}: frontmatter is not closed")
    metadata: dict[str, str] = {}
    for line in text[4:closing].splitlines():
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"{source}: invalid frontmatter line {line!r}")
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    body = text[closing + 4 :].strip()
    required = {
        "document_id",
        "title",
        "category",
        "valid_from",
        "valid_to",
        "locale",
        "source_path",
    }
    missing = sorted(required - metadata.keys())
    if missing or not body:
        raise ValueError(f"{source}: missing {', '.join(missing) if missing else 'content'}")
    return metadata, body


def load_corpus(corpus_dir: Path, expected_documents: int = 95) -> list[CorpusDocument]:
    documents: list[CorpusDocument] = []
    for path in sorted(corpus_dir.rglob("*.generated.md")):
        metadata, content = parse_frontmatter(path.read_text(encoding="utf-8"), path)
        route = path.parent.name
        if route not in INDEXES:
            raise ValueError(f"{path}: unsupported corpus route {route!r}")
        documents.append(
            CorpusDocument(
                document_id=metadata["document_id"],
                title=metadata["title"],
                property_id=metadata.get("property_id"),
                category=metadata["category"],
                valid_from=metadata["valid_from"],
                valid_to=metadata["valid_to"],
                locale=metadata["locale"],
                source_path=metadata["source_path"],
                route=route,
                content=content,
            )
        )
    if len(documents) != expected_documents:
        raise ValueError(f"Expected {expected_documents} corpus documents, found {len(documents)}")
    if len({document.document_id for document in documents}) != len(documents):
        raise ValueError("Corpus document_id values must be unique")
    return documents


def chunk_document(document: CorpusDocument, max_chars: int = 1_600) -> list[Chunk]:
    if max_chars < 400:
        raise ValueError("max_chars must be at least 400")
    words = document.content.split()
    parts: list[str] = []
    current: list[str] = []
    current_size = 0
    for word in words:
        word_size = len(word) + (1 if current else 0)
        if current and current_size + word_size > max_chars:
            parts.append(" ".join(current))
            current = [word]
            current_size = len(word)
        else:
            current.append(word)
            current_size += word_size
    if current:
        parts.append(" ".join(current))
    return [
        Chunk(
            id=_chunk_id(document.document_id, ordinal),
            document=document,
            ordinal=ordinal,
            content=content,
        )
        for ordinal, content in enumerate(parts)
    ]


def build_chunks(documents: Iterable[CorpusDocument]) -> list[Chunk]:
    return [chunk for document in documents for chunk in chunk_document(document)]


def build_index_document(chunk: Chunk, embedding: Sequence[float]) -> dict[str, object]:
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"{chunk.id}: expected {EMBEDDING_DIMENSIONS} embedding dimensions, "
            f"got {len(embedding)}"
        )
    document = chunk.document
    return {
        "id": chunk.id,
        "document_id": document.document_id,
        "title": document.title,
        "property_id": document.property_id,
        "category": document.category,
        "valid_from": document.valid_from,
        "valid_to": document.valid_to,
        "locale": document.locale,
        "source_path": document.source_path,
        "chunk_ordinal": chunk.ordinal,
        "content": chunk.content,
        "content_vector": list(embedding),
    }


def build_search_index(
    name: str,
    openai_endpoint: str,
    openai_api_key: str | None = None,
) -> SearchIndex:
    vectorizer = AzureOpenAIVectorizer(
        vectorizer_name="hotel-openai-vectorizer",
        parameters=AzureOpenAIVectorizerParameters(
            resource_url=openai_endpoint,
            deployment_name=EMBEDDING_DEPLOYMENT,
            model_name=EMBEDDING_DEPLOYMENT,
            api_key=openai_api_key,
        ),
    )
    fields = [
        SimpleField(name="id", type="Edm.String", key=True, filterable=True),
        SimpleField(name="document_id", type="Edm.String", filterable=True),
        SearchField(
            name="title",
            type="Edm.String",
            searchable=True,
            retrievable=True,
        ),
        SimpleField(name="property_id", type="Edm.String", filterable=True),
        SimpleField(name="category", type="Edm.String", filterable=True),
        SimpleField(
            name="valid_from",
            type="Edm.String",
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="valid_to",
            type="Edm.String",
            filterable=True,
            sortable=True,
        ),
        SimpleField(name="locale", type="Edm.String", filterable=True),
        SimpleField(name="source_path", type="Edm.String", filterable=True),
        SimpleField(name="chunk_ordinal", type="Edm.Int32", filterable=True),
        SearchField(
            name="content",
            type="Edm.String",
            searchable=True,
            retrievable=True,
        ),
        SearchField(
            name="content_vector",
            type="Collection(Edm.Single)",
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="hotel-vector-profile",
        ),
    ]
    return SearchIndex(
        name=name,
        fields=fields,
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hotel-hnsw")],
            profiles=[
                VectorSearchProfile(
                    name="hotel-vector-profile",
                    algorithm_configuration_name="hotel-hnsw",
                    vectorizer_name="hotel-openai-vectorizer",
                )
            ],
            vectorizers=[vectorizer],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name=SEMANTIC_CONFIGURATION_NAME,
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ],
            default_configuration_name=SEMANTIC_CONFIGURATION_NAME,
        ),
    )


def build_knowledge_source(index_name: str) -> SearchIndexKnowledgeSource:
    return SearchIndexKnowledgeSource(
        name=f"{index_name.removesuffix('-index')}-ks",
        description=f"Approved hotel corpus in {index_name}.",
        search_index_parameters=SearchIndexKnowledgeSourceParameters(
            search_index_name=index_name,
            search_fields=[SearchIndexFieldReference(name="content")],
            source_data_fields=[
                SearchIndexFieldReference(name=name)
                for name in (
                    "document_id",
                    "title",
                    "property_id",
                    "valid_from",
                    "valid_to",
                    "source_path",
                )
            ],
            semantic_configuration_name=SEMANTIC_CONFIGURATION_NAME,
        ),
    )


def build_knowledge_base(
    openai_endpoint: str,
    openai_api_key: str | None = None,
) -> KnowledgeBase:
    source_names = [f"{index.removesuffix('-index')}-ks" for index in INDEXES.values()]
    openai_parameters = {
        "resourceUri": openai_endpoint,
        "deploymentId": QUERY_PLANNING_DEPLOYMENT,
        "modelName": QUERY_PLANNING_DEPLOYMENT,
    }
    if openai_api_key:
        openai_parameters["apiKey"] = openai_api_key
    return KnowledgeBase(
        {
            "name": KNOWLEDGE_BASE_NAME,
            "description": "Approved, date-aware hotel reference knowledge.",
            "knowledgeSources": [{"name": source_name} for source_name in source_names],
            "models": [
                {
                    "kind": "azureOpenAI",
                    "azureOpenAIParameters": openai_parameters,
                }
            ],
            "outputMode": "answerSynthesis",
            "retrievalReasoningEffort": {"kind": "low"},
            "answerInstructions": (
                "Give concise answers. Cite every material statement using returned references. "
                "Never present a record outside its validity window as current."
            ),
        }
    )


def embed_chunks(openai_client: AzureOpenAI, chunks: Sequence[Chunk]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for start in range(0, len(chunks), 16):
        batch = chunks[start : start + 16]
        response = openai_client.embeddings.create(
            model=EMBEDDING_DEPLOYMENT,
            input=[chunk.content for chunk in batch],
            dimensions=EMBEDDING_DIMENSIONS,
        )
        embeddings.extend([list(item.embedding) for item in response.data])
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding response count did not match chunk count")
    return embeddings


def replace_documents(search_client: SearchClient, documents: Sequence[dict[str, object]]) -> None:
    old_ids = [result["id"] for result in search_client.search("*", select=["id"], top=1_000)]
    if old_ids:
        results = search_client.delete_documents(
            documents=[{"id": document_id} for document_id in old_ids]
        )
        _require_success(results, "delete")
    for start in range(0, len(documents), 100):
        results = search_client.merge_or_upload_documents(
            documents=list(documents[start : start + 100])
        )
        _require_success(results, "upload")


def archive_corpus(
    documents: Sequence[CorpusDocument],
    corpus_dir: Path,
    container_name: str,
    account_url: str,
) -> None:
    service = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
    container = service.get_container_client(container_name)
    for document in documents:
        source = corpus_dir.parent / document.source_path
        container.upload_blob(
            name=document.source_path,
            data=source.read_bytes(),
            overwrite=True,
            metadata={"document_id": document.document_id, "category": document.category},
        )


def verify_existing_resources(index_client: SearchIndexClient) -> None:
    missing_indexes = [name for name in INDEXES.values() if not index_client.get_index(name)]
    if missing_indexes:
        raise RuntimeError(f"Missing Search indexes: {', '.join(missing_indexes)}")
    for name in INDEXES.values():
        source_name = f"{name.removesuffix('-index')}-ks"
        source = cast(SearchIndexKnowledgeSource, index_client.get_knowledge_source(source_name))
        if source.search_index_parameters.search_index_name != name:
            raise RuntimeError(f"Knowledge source {source_name} does not reference {name}")
    knowledge_base = index_client.get_knowledge_base(KNOWLEDGE_BASE_NAME)
    source_names = {source.name for source in knowledge_base.knowledge_sources}
    expected_sources = {f"{name.removesuffix('-index')}-ks" for name in INDEXES.values()}
    if source_names != expected_sources:
        raise RuntimeError(
            "Knowledge base membership does not match the four approved knowledge sources"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=Path("foundryiq-docs"))
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate and report without Azure calls."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing index and knowledge-base definitions.",
    )
    parser.add_argument("--expected-documents", type=int, default=95)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run and args.verify_only:
        raise ValueError("--dry-run and --verify-only cannot be used together")
    corpus_dir = args.corpus_dir.resolve()
    documents = load_corpus(corpus_dir, args.expected_documents)
    chunks = build_chunks(documents)
    print(f"Validated {len(documents)} documents and {len(chunks)} chunks.")
    if args.dry_run:
        return 0

    search_endpoint = _required_environment("AZURE_SEARCH_ENDPOINT")
    credential = select_search_credential()
    index_client = SearchIndexClient(
        endpoint=search_endpoint,
        credential=credential,
        api_version="2026-05-01-preview",
    )
    if args.verify_only:
        verify_existing_resources(index_client)
        print("Foundry IQ index and knowledge-base definitions are present.")
        return 0

    openai_endpoint = _required_environment("AZURE_OPENAI_ENDPOINT")
    openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    for index_name in INDEXES.values():
        index_client.create_or_update_index(
            build_search_index(index_name, openai_endpoint, openai_api_key)
        )
    azure_credential = DefaultAzureCredential()
    openai_client = AzureOpenAI(
        azure_endpoint=openai_endpoint,
        api_version="2024-10-21",
        azure_ad_token_provider=get_bearer_token_provider(
            azure_credential, "https://cognitiveservices.azure.com/.default"
        ),
    )
    embeddings = embed_chunks(openai_client, chunks)
    documents_by_route: dict[str, list[dict[str, object]]] = {route: [] for route in INDEXES}
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        documents_by_route[chunk.document.route].append(build_index_document(chunk, embedding))
    for route, index_name in INDEXES.items():
        replace_documents(
            SearchClient(endpoint=search_endpoint, index_name=index_name, credential=credential),
            documents_by_route[route],
        )
        index_client.create_or_update_knowledge_source(build_knowledge_source(index_name))
    index_client.create_or_update_knowledge_base(
        build_knowledge_base(openai_endpoint, openai_api_key)
    )

    container_name = os.getenv("FOUNDRY_IQ_BLOB_CONTAINER")
    account_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL")
    if container_name or account_url:
        if not container_name or not account_url:
            raise RuntimeError(
                "Set both FOUNDRY_IQ_BLOB_CONTAINER and AZURE_STORAGE_ACCOUNT_URL for archival."
            )
        archive_corpus(documents, corpus_dir, container_name, account_url)
    print(f"Created or updated {len(INDEXES)} indexes and {KNOWLEDGE_BASE_NAME}.")
    return 0


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required for live Foundry IQ operations.")
    return value


def _chunk_id(document_id: str, ordinal: int) -> str:
    digest = hashlib.sha256(document_id.encode("utf-8")).hexdigest()[:12]
    return f"{digest}-{ordinal:03d}"


def _require_success(results: Iterable[Any], operation: str) -> None:
    failures = [result for result in results if not getattr(result, "succeeded", False)]
    if failures:
        details = ", ".join(str(getattr(result, "error_message", result)) for result in failures)
        raise RuntimeError(f"Search {operation} failed: {details}")


if __name__ == "__main__":
    raise SystemExit(main())
