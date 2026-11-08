from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import setup_foundry_iq
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.credentials import select_azure_credential
from hotel_servicing_agent.tools.foundry_iq import FoundryIQTool
from setup_foundry_iq import (
    EMBEDDING_DIMENSIONS,
    Chunk,
    CorpusDocument,
    _required_environment,
    build_chunks,
    build_index_document,
    build_knowledge_base,
    build_search_index,
    load_corpus,
    parse_frontmatter,
    replace_documents,
    verify_canonical_corpus,
    verify_indexed_documents,
)


def test_parse_frontmatter_and_route_chunks() -> None:
    source = Path("foundryiq-docs/properties/HTL-001.profile.generated.md")
    metadata, content = parse_frontmatter(source.read_text(encoding="utf-8"), source)

    assert metadata["document_id"] == "DOC-PROP-HTL-001"
    assert "Permanent property facts" in content
    documents = load_corpus(Path("foundryiq-docs"))
    chunks = build_chunks(documents)

    assert len(documents) == 95
    assert len(chunks) >= 95
    assert {chunk.document.route for chunk in chunks} == {
        "properties",
        "policies",
        "dining-local",
        "operations",
    }


def test_build_index_document_preserves_isolation_and_temporal_metadata() -> None:
    document = CorpusDocument(
        document_id="DOC-1",
        title="A title",
        property_id="HTL-001",
        category="dated_notice",
        valid_from="2026-04-01",
        valid_to="2026-04-21",
        locale="en-US",
        source_path="foundryiq-docs/operations/notice.md",
        route="operations",
        content="A dated notice.",
    )
    chunk = Chunk(id="chunk-1", document=document, ordinal=0, content=document.content)

    indexed = build_index_document(chunk, [0.0] * EMBEDDING_DIMENSIONS)

    assert indexed["property_id"] == "HTL-001"
    assert indexed["valid_to"] == "2026-04-21"
    assert indexed["content_vector"] == [0.0] * EMBEDDING_DIMENSIONS
    with pytest.raises(ValueError, match="1536"):
        build_index_document(chunk, [0.0])


def test_openai_key_fallback_is_explicit_and_never_required() -> None:
    index_without_key = build_search_index("hotel-test-index", "https://model.example.test")
    index_with_key = build_search_index(
        "hotel-test-index",
        "https://model.example.test",
        "test-key",
    )
    knowledge_base = build_knowledge_base("https://model.example.test", "test-key")

    assert (
        "apiKey"
        not in index_without_key.as_dict()["vectorSearch"]["vectorizers"][0][
            "azureOpenAIParameters"
        ]
    )
    assert (
        index_with_key.as_dict()["vectorSearch"]["vectorizers"][0]["azureOpenAIParameters"][
            "apiKey"
        ]
        == "test-key"
    )
    assert knowledge_base.as_dict()["models"][0]["azureOpenAIParameters"]["apiKey"] == "test-key"
    assert knowledge_base.as_dict()["retrievalReasoningEffort"]["kind"] == "low"


def test_native_index_has_semantic_search_without_vectors() -> None:
    native = build_search_index(
        "hotel-test-index", "https://model.example.test", retrieval_mode="native"
    ).as_dict()
    indexed = build_index_document(build_chunks(load_corpus(Path("foundryiq-docs")))[0])

    assert "vectorSearch" not in native
    assert "content_vector" not in {field["name"] for field in native["fields"]}
    assert "content_vector" not in indexed
    assert native["semantic"]["defaultConfiguration"] == "hotel-semantic"
    assert native["semantic"]["configurations"][0]["prioritizedFields"][
        "prioritizedContentFields"
    ] == [{"fieldName": "content"}]
    with pytest.raises(ValueError, match="native or vector"):
        build_search_index("hotel-test-index", "", retrieval_mode="invalid")


def test_canonical_check_rejects_missing_extra_and_stale_sources(tmp_path: Path) -> None:
    setup_foundry_iq.generate_documents(tmp_path)
    verify_canonical_corpus(tmp_path)
    source = tmp_path / "properties" / "HTL-001.profile.generated.md"
    original = source.read_bytes()
    source.write_bytes(original.replace(b"\n", b"\r\n"))
    verify_canonical_corpus(tmp_path)
    source.write_bytes(original + b"\nStale content.\n")
    with pytest.raises(ValueError, match="HTL-001.profile.generated.md"):
        verify_canonical_corpus(tmp_path)
    source.unlink()
    with pytest.raises(ValueError, match="HTL-001.profile.generated.md"):
        verify_canonical_corpus(tmp_path)
    source.write_bytes(original)
    extra = tmp_path / "properties" / "extra.generated.md"
    extra.write_bytes(original)
    with pytest.raises(ValueError, match="extra.generated.md"):
        verify_canonical_corpus(tmp_path)


def test_corpus_source_path_must_match_actual_document(tmp_path: Path) -> None:
    source = Path("foundryiq-docs/properties/HTL-001.profile.generated.md")
    target = tmp_path / "properties" / source.name
    target.parent.mkdir()
    target.write_text(
        source.read_text(encoding="utf-8").replace(
            f"foundryiq-docs/properties/{source.name}", "../../outside.md"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="source_path must match"):
        load_corpus(tmp_path, expected_documents=1)


@pytest.mark.parametrize("field", ["content", "source_path", "property_id", "valid_to"])
def test_index_verification_checks_content_and_metadata(field: str) -> None:
    chunks = build_chunks(load_corpus(Path("foundryiq-docs")))
    documents = [build_index_document(chunk) for chunk in chunks]
    client = SimpleNamespace(search=lambda *_, **__: documents)
    verify_indexed_documents(client, chunks)
    documents[0][field] = "incorrect"
    with pytest.raises(RuntimeError, match="content, or source metadata"):
        verify_indexed_documents(client, chunks)


def test_index_verification_rejects_missing_extra_and_duplicate_records() -> None:
    chunks = build_chunks(load_corpus(Path("foundryiq-docs")))
    documents = [build_index_document(chunk) for chunk in chunks]
    client = SimpleNamespace(search=lambda *_, **__: documents)
    missing = documents.pop()
    with pytest.raises(RuntimeError, match="document IDs"):
        verify_indexed_documents(client, chunks)
    documents.append(missing)
    documents.append(dict(missing, id="unexpected"))
    with pytest.raises(RuntimeError, match="unexpected"):
        verify_indexed_documents(client, chunks)
    documents[-1] = dict(missing)
    with pytest.raises(RuntimeError, match="Duplicate"):
        verify_indexed_documents(client, chunks)


def test_populated_index_replacement_requires_explicit_permission() -> None:
    captured: list[str] = []
    client = SimpleNamespace(
        search=lambda *_, **__: [{"id": "old"}],
        delete_documents=lambda **_: captured.append("delete") or [],
        merge_or_upload_documents=lambda **_: (
            captured.append("upload") or [SimpleNamespace(succeeded=True)]
        ),
    )
    with pytest.raises(RuntimeError, match="--replace-existing"):
        replace_documents(client, [{"id": "new"}])
    assert captured == []
    replace_documents(client, [{"id": "new"}], replace_existing=True)
    assert captured == ["delete", "upload"]


def test_native_setup_never_constructs_an_embedding_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    indexes: list[dict[str, Any]] = []
    uploads: dict[str, list[dict[str, object]]] = {}
    sources: list[str] = []
    bases: list[str] = []
    index_client = SimpleNamespace(
        list_index_names=lambda: [],
        create_or_update_index=lambda index: indexes.append(index.as_dict()),
        create_or_update_knowledge_source=lambda source: sources.append(source.name),
        create_or_update_knowledge_base=lambda base: bases.append(base.name),
    )

    def search_factory(*, index_name: str, **_: object) -> object:
        return SimpleNamespace(
            search=lambda *_, **__: [],
            merge_or_upload_documents=lambda *, documents: (
                uploads.setdefault(index_name, documents)
                and [SimpleNamespace(succeeded=True) for _ in documents]
            ),
        )

    monkeypatch.setattr(
        setup_foundry_iq,
        "parse_args",
        lambda: SimpleNamespace(
            corpus_dir=Path("foundryiq-docs"),
            expected_documents=95,
            dry_run=False,
            verify_only=False,
            check_canonical=False,
            retrieval_mode="native",
            replace_existing=False,
        ),
    )
    monkeypatch.setattr(setup_foundry_iq, "SearchIndexClient", lambda **_: index_client)
    monkeypatch.setattr(setup_foundry_iq, "SearchClient", search_factory)
    monkeypatch.setattr(setup_foundry_iq, "select_search_credential", lambda: object())
    monkeypatch.setattr(
        setup_foundry_iq,
        "AzureOpenAI",
        lambda **_: pytest.fail("Native mode must not construct an embedding client"),
    )
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.test")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://model.example.test")
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FOUNDRY_IQ_BLOB_CONTAINER", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_ACCOUNT_URL", raising=False)

    assert setup_foundry_iq.main() == 0
    assert len(indexes) == 4
    assert all("vectorSearch" not in index for index in indexes)
    assert {name: len(documents) for name, documents in uploads.items()} == {
        "hotel-properties-index": 20,
        "hotel-policies-index": 15,
        "hotel-dining-local-index": 20,
        "hotel-operations-index": 40,
    }
    assert all("content_vector" not in document for docs in uploads.values() for document in docs)
    assert set(sources) == {
        "hotel-properties-ks",
        "hotel-policies-ks",
        "hotel-dining-local-ks",
        "hotel-operations-ks",
    }
    assert bases == ["hotel-foundryiq"]


def test_live_setup_requires_explicit_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)

    with pytest.raises(RuntimeError, match="AZURE_SEARCH_ENDPOINT"):
        _required_environment("AZURE_SEARCH_ENDPOINT")


def test_runtime_credential_selection_uses_managed_identity_only_when_signaled() -> None:
    local = select_azure_credential({})
    hosted = select_azure_credential(
        {"IDENTITY_ENDPOINT": "http://identity", "AZURE_CLIENT_ID": "id"}
    )

    assert isinstance(local, DefaultAzureCredential)
    assert isinstance(hosted, ManagedIdentityCredential)


def test_settings_requires_foundry_iq_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    instructions = tmp_path / "instructions.md"
    instructions.write_text("Instructions", encoding="utf-8")
    monkeypatch.setenv(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://project.example.test/api/projects/hotel",
    )
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("AGENT_INSTRUCTIONS_PATH", str(instructions))
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)

    with pytest.raises(RuntimeError, match="AZURE_SEARCH_ENDPOINT"):
        Settings.from_environment()


def test_tool_serializes_answer_and_references_without_network() -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def retrieve(self, retrieval_request: object) -> object:
            captured["request"] = retrieval_request
            return SimpleNamespace(
                response=[
                    SimpleNamespace(
                        content=[SimpleNamespace(text="Pool hours are 06:00-22:00 [ref_id:0].")]
                    )
                ],
                references=[
                    SimpleNamespace(
                        id="0",
                        doc_key="chunk-1",
                        source_data={
                            "title": "Property profile",
                            "property_id": "HTL-001",
                            "valid_from": "2026-01-01",
                            "valid_to": "2026-12-31",
                            "source_path": "foundryiq-docs/properties/HTL-001.profile.generated.md",
                        },
                    )
                ],
            )

    def fake_factory(**kwargs: object) -> FakeClient:
        captured["factory"] = kwargs
        return FakeClient()

    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=fake_factory,
    )
    result = json.loads(
        tool.search("What are pool hours?", property_id="HTL-001", as_of="2026-04-10")
    )

    assert result["answer"].endswith("[ref_id:0].")
    assert result["references"][0]["source_path"].endswith("HTL-001.profile.generated.md")
    assert result["references"][0]["property_id"] == "HTL-001"
    assert result["references"][0]["valid_to"] == "2026-12-31"
    assert result["property"] == {
        "property_id": "HTL-001",
        "official_name": "Hotel Seattle Waterfront",
    }
    factory = captured["factory"]
    assert factory["endpoint"] == "https://search.example.test"
    assert factory["knowledge_base_name"] == "hotel-foundryiq"
    assert factory["api_version"] == "2026-05-01-preview"
    request = captured["request"]
    assert (
        "property_id eq 'HTL-001'" in request.as_dict()["knowledgeSourceParams"][0]["filterAddOn"]
    )
    assert (
        "property_id eq 'chain-wide'"
        in request.as_dict()["knowledgeSourceParams"][0]["filterAddOn"]
    )


def test_cross_source_reservation_lookup_requires_matching_fabric_confirmation() -> None:
    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: pytest.fail("Retrieval must not run for an unverified property"),
    )

    with pytest.raises(ValueError, match="first wait for the Fabric result"):
        tool.search(
            "For the property associated with reservation RES-123, give pool hours.",
            property_id="HTL-001",
        )
    with pytest.raises(ValueError, match="must exactly match"):
        tool.search(
            "Confirmed from Fabric: HTL-004. For reservation RES-123, give property pool hours.",
            property_id="HTL-001",
        )
