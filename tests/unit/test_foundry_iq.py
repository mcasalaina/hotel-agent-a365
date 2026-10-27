from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import setup_foundry_iq
import verify_deployment
from azure.core.exceptions import HttpResponseError
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from hotel_servicing_agent.config import Settings
from hotel_servicing_agent.credentials import select_azure_credential
from hotel_servicing_agent.property_catalog import PROPERTY_NAMES
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
    validate_deployment_corpus,
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


def test_lexical_index_needs_no_embedding_deployment() -> None:
    index = build_search_index(
        "hotel-properties-index",
        "https://model.example.test",
        include_vectors=False,
    ).as_dict()
    document = load_corpus(Path("foundryiq-docs"))[0]
    indexed = build_index_document(build_chunks([document])[0], None)

    assert "vectorSearch" not in index
    assert "content_vector" not in {field["name"] for field in index["fields"]}
    assert "content_vector" not in indexed
    assert index["semantic"]["defaultConfiguration"] == "hotel-semantic"
    assert indexed["content"]


def test_lexical_setup_uses_explicit_cli_tenant_for_search_and_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {"indexes": [], "sources": [], "documents": []}
    credential = object()
    original = load_corpus(Path("foundryiq-docs"))[0]
    documents = [
        replace(original, document_id=f"DOC-{index}", route=route)
        for index, route in enumerate(list(setup_foundry_iq.INDEXES) * 24)
    ][:95]

    def cli_credential(**kwargs: object) -> object:
        captured["credential_options"] = kwargs
        return credential

    class FakeIndexClient:
        def __init__(self, **kwargs: object) -> None:
            captured["index_client"] = kwargs

        def create_or_update_index(self, index: object) -> None:
            captured["indexes"].append(index.as_dict())

        def create_or_update_knowledge_source(self, source: object) -> None:
            captured["sources"].append(source.as_dict())

        def create_or_update_knowledge_base(self, knowledge_base: object) -> None:
            captured["knowledge_base"] = knowledge_base.as_dict()

    class FakeSearchClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["credential"] is credential

        def search(self, *args: object, **kwargs: object) -> list[object]:
            return []

        def merge_or_upload_documents(self, documents: list[dict[str, object]]) -> list[object]:
            captured["documents"].extend(documents)
            return [SimpleNamespace(succeeded=True) for _ in documents]

    def archive(*args: object) -> None:
        captured["archive"] = args

    monkeypatch.setattr(
        setup_foundry_iq,
        "parse_args",
        lambda: SimpleNamespace(
            corpus_dir=Path("foundryiq-docs"),
            expected_documents=95,
            dry_run=False,
            verify_only=False,
            lexical_only=True,
            tenant_id="target-tenant",
        ),
    )
    monkeypatch.setattr(setup_foundry_iq, "AzureCliCredential", cli_credential)
    monkeypatch.setattr(setup_foundry_iq, "load_corpus", lambda *_: documents)
    monkeypatch.setattr(
        setup_foundry_iq,
        "DefaultAzureCredential",
        lambda: pytest.fail("Explicit CLI authentication must not use a credential chain"),
    )
    monkeypatch.setattr(
        setup_foundry_iq,
        "AzureOpenAI",
        lambda **_: pytest.fail("Lexical setup must not call an embedding model"),
    )
    monkeypatch.setattr(setup_foundry_iq, "SearchIndexClient", FakeIndexClient)
    monkeypatch.setattr(setup_foundry_iq, "SearchClient", FakeSearchClient)
    monkeypatch.setattr(setup_foundry_iq, "archive_corpus", archive)
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://search.example.test")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://model.example.test")
    monkeypatch.setenv("FOUNDRY_IQ_BLOB_CONTAINER", "hotel-docs")
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT_URL", "https://archive.example.test")
    monkeypatch.setenv("AZURE_SEARCH_ADMIN_KEY", "ignored-with-explicit-tenant")

    assert setup_foundry_iq.main() == 0
    assert captured["credential_options"] == {"tenant_id": "target-tenant"}
    assert captured["index_client"]["credential"] is credential
    assert captured["archive"][-1] is credential
    assert len(captured["indexes"]) == 4
    assert len(captured["sources"]) == 4
    assert len(captured["documents"]) >= 95
    assert all("content_vector" not in document for document in captured["documents"])
    assert all("vectorSearch" not in index for index in captured["indexes"])
    assert (
        captured["knowledge_base"]["models"][0]["azureOpenAIParameters"]["deploymentId"]
        == "gpt-5.4-mini"
    )


@pytest.mark.parametrize("label", ["demo", "synthetic", "TEST", "sample", "fictional"])
def test_deployment_corpus_rejects_runtime_labels(label: str) -> None:
    document = load_corpus(Path("foundryiq-docs"))[0]
    validate_deployment_corpus([document])
    with pytest.raises(ValueError, match="runtime-prohibited source labels"):
        validate_deployment_corpus([replace(document, content=f"This is {label} content.")])


def test_live_setup_requires_explicit_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)

    with pytest.raises(RuntimeError, match="AZURE_SEARCH_ENDPOINT"):
        _required_environment("AZURE_SEARCH_ENDPOINT")


@pytest.mark.parametrize("include_vectors", [False, True])
def test_deployment_verification_uses_each_live_index_schema(
    monkeypatch: pytest.MonkeyPatch, include_vectors: bool
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeIndexClient:
        def get_index(self, name: str) -> Any:
            return build_search_index(
                name, "https://model.example.test", include_vectors=include_vectors
            )

    class FakeSearchClient:
        def __init__(self, endpoint: str, index_name: str, credential: object) -> None:
            self.index_name = index_name

        def search(self, *args: object, **kwargs: Any) -> list[dict[str, object]]:
            calls.append((self.index_name, kwargs))
            return [{"id": "row-1", "property_id": "HTL-001"}]

    monkeypatch.setattr(verify_deployment, "SearchClient", FakeSearchClient)

    counts, isolation, modes = verify_deployment.verify_direct_searches(
        "https://search.example.test",
        object(),
        "HTL-001",
        index_client=FakeIndexClient(),
    )

    assert isolation == {"properties": 1}
    assert set(modes) == set(setup_foundry_iq.INDEXES)
    expected_mode = "vector_semantic" if include_vectors else "semantic_lexical"
    assert set(modes.values()) == {expected_mode}
    vector_calls = [(name, options) for name, options in calls if "vector_queries" in options]
    assert len(vector_calls) == (4 if include_vectors else 0)
    if include_vectors:
        assert {name for name, _ in vector_calls} == set(setup_foundry_iq.INDEXES.values())
        assert all(
            options["vector_queries"][0].fields == "content_vector" for _, options in vector_calls
        )
    assert len(counts) == (8 if include_vectors else 4)
    semantic_calls = [options for _, options in calls if options.get("query_type") == "semantic"]
    assert len(semantic_calls) == 4


@pytest.mark.parametrize("failure", ["error", "empty"])
def test_deployment_verification_does_not_hide_vector_failures(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    class FakeIndexClient:
        def get_index(self, name: str) -> Any:
            return build_search_index(
                name,
                "https://model.example.test",
                include_vectors=name == setup_foundry_iq.INDEXES["operations"],
            )

    class FakeSearchClient:
        def __init__(self, *args: object) -> None:
            pass

        def search(self, *args: object, **kwargs: Any) -> list[dict[str, object]]:
            if "vector_queries" in kwargs:
                if failure == "error":
                    raise HttpResponseError(message="Vectorizer unavailable")
                return []
            return [{"id": "row-1", "property_id": "HTL-001"}]

    monkeypatch.setattr(verify_deployment, "SearchClient", FakeSearchClient)
    exception = HttpResponseError if failure == "error" else RuntimeError
    with pytest.raises(exception, match="Vectorizer unavailable|vector query returned no results"):
        verify_deployment.verify_direct_searches(
            "https://search.example.test",
            object(),
            "HTL-001",
            index_client=FakeIndexClient(),
        )


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


def test_knowledge_tool_exposes_canonical_roster_without_requiring_operations_lookup() -> None:
    tool = FoundryIQTool("https://search.example.test", "hotel-foundryiq", object())
    description = tool.as_function_tool().description

    for property_id, name in PROPERTY_NAMES.items():
        assert f"{name} = {property_id}" in description
    assert "Never guess property_id" in description
    assert "omit property_id when it is unknown" in description
    assert "without an operations-data lookup" in description
    assert "Confirmed from Fabric: HTL-###" in description


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
    assert "use the user's established conversation language" in result["response_guidance"]
    assert "references[].title" in result["response_guidance"]
    assert "references[].valid_from effective date" in result["response_guidance"]
    assert "Quoting a policy sentence is not a substitute" in result["response_guidance"]
    assert (
        "Preserve the official document title verbatim as a proper name"
        in (result["response_guidance"])
    )
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


@pytest.mark.parametrize(
    "question",
    [
        "María and Chen are visiting Lyrenza Scottsdale Sonoran Resort. "
        "What is the nightly valet parking fee? Cite the hotel policy.",
        "José and Wei are visiting Lyrenza Scottsdale Sonoran Resort. "
        "What is the nightly valet parking fee? Cite the hotel policy.",
        "Élodie and François are visiting Lyrenza Scottsdale Sonoran Resort. "
        "What is the nightly valet parking fee? Cite the hotel policy.",
        "Répondez en français : María et Chen séjournent au Lyrenza Scottsdale Sonoran Resort. "
        "Quel est le tarif du voiturier par nuit ? Citez la source.",
        "Maria García séjourne au Lyrenza Scottsdale Sonoran Resort. "
        "Quel est le tarif du voiturier par nuit ? Citez la source.",
        "¿Cuánto cuesta el valet en Lyrenza Scottsdale Sonoran Resort? Cita la fuente.",
        "Lyrenza Scottsdale Sonoran Resort 的代客泊车每晚收费多少美元？请引用酒店资料。",
        "ما سعر خدمة صف السيارات لكل ليلة في Lyrenza Scottsdale Sonoran Resort؟ اذكر المصدر.",
    ],
)
def test_knowledge_response_preserves_user_question_and_language_citation_contract(
    question: str,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def retrieve(self, retrieval_request: Any) -> object:
            captured["question"] = retrieval_request.as_dict()["messages"][0]["content"][0]["text"]
            return SimpleNamespace(
                response=[SimpleNamespace(content=[SimpleNamespace(text="Valet USD 25 nightly.")])],
                references=[
                    SimpleNamespace(
                        id="0",
                        doc_key="property-profile",
                        source_data={
                            "title": "Lyrenza Scottsdale Sonoran Resort property profile",
                            "property_id": "HTL-004",
                            "valid_from": "2026-03-01",
                            "valid_to": "2099-12-31",
                        },
                    )
                ],
            )

    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: FakeClient(),
    )
    result = json.loads(tool.search(question, property_id="HTL-004", as_of="2026-09-01"))

    assert captured["question"] == question
    assert result["references"][0]["title"] == "Lyrenza Scottsdale Sonoran Resort property profile"
    assert result["references"][0]["valid_from"] == "2026-03-01"
    guidance = result["response_guidance"]
    assert "An English utterance requires an English response" in guidance
    assert "do not infer a visitor's preferred language" in guidance
    assert "A Spanish utterance requires a Spanish response" in guidance
    assert "an Arabic utterance requires an Arabic response" in guidance
    assert "references[].title" in guidance
    assert "references[].valid_from effective date" in guidance
    assert "Quoting a policy sentence is not a substitute" in guidance


def test_property_name_applies_property_filter_without_model_supplied_id() -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def retrieve(self, retrieval_request: object) -> object:
            captured["request"] = retrieval_request
            return SimpleNamespace(
                response=[
                    SimpleNamespace(
                        content=[SimpleNamespace(text="The policy does not list a price.")]
                    )
                ],
                references=[
                    SimpleNamespace(
                        id="policy",
                        doc_key="policy-chunk",
                        source_data={
                            "title": "Chain-wide parking procedure",
                            "property_id": "chain-wide",
                            "valid_from": "2026-03-01",
                            "valid_to": "2099-12-31",
                            "source_path": "foundryiq-docs/policies/parking.generated.md",
                        },
                    )
                ],
            )

    class FakeSearchClient:
        def search(self, **kwargs: object) -> list[dict[str, object]]:
            captured["search"] = kwargs
            return [
                {
                    "id": "chunk-4",
                    "document_id": "DOC-PROP-HTL-004",
                    "title": "Lyrenza Scottsdale Sonoran Resort property profile",
                    "property_id": "HTL-004",
                    "valid_from": "2026-03-01",
                    "valid_to": "2099-12-31",
                    "source_path": "foundryiq-docs/properties/HTL-004.profile.generated.md",
                    "content": "Parking: Self parking included; valet USD 25 nightly.",
                }
            ]

    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: FakeClient(),
        search_client_factory=lambda **_: FakeSearchClient(),
    )

    result = json.loads(
        tool.search(
            "What is the valet parking price at Lyrenza Scottsdale Sonoran Resort?",
            property_id="HTL-005",
            as_of="2026-09-01",
        )
    )

    request = captured["request"]
    assert (
        "property_id eq 'HTL-004'" in request.as_dict()["knowledgeSourceParams"][0]["filterAddOn"]
    )
    assert result["property"] == {
        "property_id": "HTL-004",
        "official_name": "Lyrenza Scottsdale Sonoran Resort",
    }
    assert "valet USD 25 nightly" in result["answer"]
    assert result["answer"].endswith("[ref_id:0]")
    assert result["references"][0]["document_id"] == "DOC-PROP-HTL-004"
    search = captured["search"]
    assert search["search_text"] == "*"
    assert "property_id eq 'HTL-004'" in search["filter"]


def test_property_profile_fallback_handles_knowledge_base_failure() -> None:
    class FailingClient:
        def retrieve(self, retrieval_request: object) -> object:
            raise HttpResponseError(message="Knowledge-base model unavailable")

    class FakeSearchClient:
        def search(self, **kwargs: object) -> list[dict[str, object]]:
            return [
                {
                    "id": "chunk-4",
                    "document_id": "DOC-PROP-HTL-004",
                    "title": "Lyrenza Scottsdale Sonoran Resort property profile",
                    "property_id": "HTL-004",
                    "valid_from": "2026-03-01",
                    "valid_to": "2099-12-31",
                    "source_path": "foundryiq-docs/properties/HTL-004.profile.generated.md",
                    "content": "Parking: Self parking included; valet USD 25 nightly.",
                }
            ]

    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: FailingClient(),
        search_client_factory=lambda **_: FakeSearchClient(),
    )

    result = json.loads(
        tool.search(
            "What is the valet parking price at Lyrenza Scottsdale Sonoran Resort?",
            as_of="2026-09-01",
        )
    )

    assert "valet USD 25 nightly" in result["answer"]
    assert result["answer"].endswith("[ref_id:0]")
    assert result["references"][0]["property_id"] == "HTL-004"
    assert "references[].title" in result["response_guidance"]
    assert "references[].valid_from effective date" in result["response_guidance"]


@pytest.mark.parametrize(
    "question",
    [
        "What is the valet rate at the Scottsdale property?",
        "Does the Sonoran resort offer valet parking?",
        "What parking is available at HTL-004?",
    ],
)
def test_abbreviated_property_reference_applies_unique_filter(question: str) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def retrieve(self, retrieval_request: object) -> object:
            captured["request"] = retrieval_request
            return SimpleNamespace(response=[], references=[])

    class FakeSearchClient:
        def search(self, **_: object) -> list[dict[str, object]]:
            return []

    tool = FoundryIQTool(
        "https://search.example.test",
        "hotel-foundryiq",
        object(),
        client_factory=lambda **_: FakeClient(),
        search_client_factory=lambda **_: FakeSearchClient(),
    )

    tool.search(question, as_of="2026-09-01")

    request = captured["request"]
    assert (
        "property_id eq 'HTL-004'" in request.as_dict()["knowledgeSourceParams"][0]["filterAddOn"]
    )
