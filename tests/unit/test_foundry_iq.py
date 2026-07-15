from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
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
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://project.example.test")
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
        "official_name": "Lyrenza Seattle Waterfront",
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
