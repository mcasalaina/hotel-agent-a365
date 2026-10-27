from __future__ import annotations

import importlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "evaluation/assert"))

assets = importlib.import_module("recreate_foundry_evaluation_assets")
quality = importlib.import_module("run_foundry_agent_quality")
multilingual = importlib.import_module("run_multilingual_evaluator_quality")
hosted = importlib.import_module("run_hosted_knowledge_quality")


def test_hosted_capture_parses_actual_response_identifiers():
    response = {
        "id": "resp-captured",
        "conversation": {"id": "conv-captured"},
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Actual answer"}]}
        ],
    }
    raw = (
        "HTTP/2 200 OK\nX-Ms-Agent-Session-Id: session-captured\n"
        "Request-Id: request-captured\nSet-Cookie: excluded\n\n" + json.dumps(response)
    )
    captured = hosted.parse_invocation(raw)
    assert captured["responseId"] == "resp-captured"
    assert captured["conversationId"] == "conv-captured"
    assert captured["sessionId"] == "session-captured"
    assert captured["actualResponse"] == "Actual answer"
    assert "set-cookie" not in captured["responseHeaders"]


@pytest.mark.parametrize("continuation_session", ["session-real", "session-wrong"])
def test_hosted_capture_pins_every_turn_and_checks_continuity(tmp_path, continuation_session):
    calls = []

    def invoke(command, **kwargs):
        calls.append(command)
        session = "session-real" if len(calls) == 1 else continuation_session
        response = {
            "id": f"response-{len(calls)}",
            "conversation": {"id": "conversation-real"},
            "agent_reference": {
                "type": "agent_reference",
                "name": hosted.AGENT,
                "version": hosted.VERSION,
            },
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "USD 25"}]}],
        }
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=f"HTTP/2 200 OK\nX-Ms-Agent-Session-Id: {session}\n\n{json.dumps(response)}",
        )

    with (
        patch.object(hosted, "ARTIFACTS", tmp_path),
        patch.object(hosted, "CASES", hosted.CASES[:2]),
        patch.object(hosted.subprocess, "run", side_effect=invoke),
        patch.dict("os.environ", {"AZURE_DEV_USER_AGENT": "microsoft_foundry_skill"}),
    ):
        if continuation_session == "session-wrong":
            with pytest.raises(RuntimeError, match="continuation changed"):
                hosted.capture(None)
        else:
            hosted.capture(None)
        assert len(calls) == 2
        assert all(command[command.index("--version") + 1] == hosted.VERSION for command in calls)
        assert "--new-session" in calls[0]
        assert "--conversation-id" in calls[1]
        assert "--session-id" not in calls[1]
        assert (tmp_path / "raw" / f"{hosted.CASES[1]['id']}.txt").is_file()


def test_hosted_knowledge_fact_checks_normalize_arabic_digits():
    result = hosted.knowledge_scores("٢٥ دولارًا لكل ليلة؛ ٠٧:٠٠ إلى ٢١:٠٠", ["valet", "pool"])
    assert all(item["score"] == 1 for item in result.values())


@pytest.mark.parametrize(
    "answer",
    [
        "Pool hours are 07:00–21:00.Pool hours are 07:00–21:00.",
        "Pool hours are 07:00–21:00.\n\nPool hours are 07:00–21:00.",
        "Pool opens at seven. Valet is USD 25. Pool opens at seven. Valet is USD 25.",
        "El valet cuesta USD 25 por noche. El valet cuesta USD 25 por noche.",
        "泳池开放时间为07:00至21:00。泳池开放时间为07:00至21:00。",
        "السعر ٢٥ دولارًا لكل ليلة. السعر ٢٥ دولارًا لكل ليلة.",
        "Parking costs USD 25\n\nParking costs USD 25\n\nOther policy",
    ],
)
def test_hosted_duplicate_text_fails_repeated_sentences_and_paragraphs(answer):
    result = hosted.duplicate_text_assertion(answer)
    assert result["passed"] is False
    assert result["score"] == 0
    assert result["matches"]


@pytest.mark.parametrize(
    "answer",
    [
        "Valet is USD 25 per night. The pool is open 07:00–21:00.",
        "Pool hours are 07:00–21:00.\n\nSource: Scottsdale amenities.",
        "泳池开放时间为07:00至21:00。代客泊车每晚25美元。",
        "السعر ٢٥ دولارًا لكل ليلة. المصدر: سياسة الفندق.",
    ],
)
def test_hosted_duplicate_text_accepts_distinct_factual_sentences(answer):
    assert hosted.duplicate_text_assertion(answer) == {
        "passed": True,
        "score": 1,
        "matches": [],
    }


def test_hosted_run_inventory_does_not_confuse_static_v2_with_agent_v2():
    before = {
        "language": {
            "data": [
                {"name": "hotel-language-continuity-quality-v2-r3-static"},
                {"name": f"hotel-2701-agent-v{hosted.VERSION}-language-actual"},
                {
                    "name": "actual-capture",
                    "metadata": {
                        "agent_name": hosted.AGENT,
                        "agent_version": hosted.VERSION,
                    },
                },
            ]
        }
    }
    assert len(hosted.existing_version_runs(before)) == 2


def test_hosted_capture_validation_rejects_reused_ids_and_other_versions():
    records = [
        {
            **case,
            "agentName": hosted.AGENT,
            "agentVersion": hosted.VERSION,
            "agentInvoked": True,
            "responseId": f"response-{case['id']}",
            "sessionId": f"session-{case['conversation']}",
            "conversationId": f"conversation-{case['conversation']}",
        }
        for case in hosted.CASES
    ]
    with patch.object(hosted, "save") as save, patch.object(Path, "exists", return_value=False):
        hosted.validate_captures(records)
        assert save.call_args.args[1]["actualCaseCount"] == 8
        records[0]["agentVersion"] = "other-version"
        with pytest.raises(RuntimeError, match="selected actual-agent case/version"):
            hosted.validate_captures(records)
        records[0]["agentVersion"] = hosted.VERSION
        records[0]["responseId"] = records[1]["responseId"]
        with pytest.raises(RuntimeError, match="response ID has been reused"):
            hosted.validate_captures(records)


def test_hosted_failure_analysis_separates_agent_and_evaluator_scope_errors():
    record = {
        "actualResponse": "Actual generated answer",
        "observations": {"invokedTools": ["search_hotel_knowledge"]},
        "verdicts": {
            "duplicateTextPassed": True,
            "languageDetectedPassed": True,
            "knowledgeFactsPassed": True,
            "knowledgeOnlyRoutePassed": True,
            "propertyIdentityPassed": False,
        },
        "evaluations": {
            "knowledge": {
                "results": [
                    {"name": "temporal-boundary", "passed": False, "reason": "Not a date query"},
                    {
                        "name": "hotel-agent-rubric",
                        "passed": False,
                        "reason": "Generic source",
                        "properties": {
                            "dimension_scores": [
                                {"id": "work_iq_delegated_protocol", "applicable": True}
                            ]
                        },
                    },
                ]
            }
        },
    }
    findings = hosted.failure_analysis(record)
    assert [finding["classification"] for finding in findings] == [
        "rubric/evaluator",
        "agent behavior and rubric/evaluator",
        "agent behavior",
    ]
    assert findings[0]["applicable"] is False
    assert findings[1]["applicabilityCaveat"]
    assert findings[2]["source"] == "propertyIdentityPassed"
    assert all(finding["actualOutput"] == record["actualResponse"] for finding in findings)


def test_hosted_transcript_conversion_preserves_actual_content():
    actual = [
        {
            "type": "function_call",
            "call_id": "call-real",
            "name": "search_hotel_knowledge",
            "arguments": '{"question":"pool hours"}',
        },
        {"type": "function_call_output", "call_id": "call-real", "output": "Actual source"},
        {
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "output_text", "text": "Actual generated answer"},
            ],
        },
    ]
    messages = hosted.transcript_messages(actual)
    assert [message["role"] for message in messages] == ["assistant", "tool", "assistant"]
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == actual[0]["arguments"]
    assert messages[1]["content"] == actual[1]["output"]
    assert messages[2]["content"] == "Actual generated answer"
    normalized = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_call", "tool_call": messages[0]["tool_calls"][0]},
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-real",
            "content": [{"type": "tool_result", "tool_result": "Actual source"}],
        },
        messages[2],
    ]
    assert hosted.canonical_messages(normalized) == hosted.canonical_messages(messages)
    original_call = messages[0]["tool_calls"][0]
    normalized[0]["content"][0]["tool_call"] = {
        **original_call,
        "function": {
            **original_call["function"],
            "arguments": {"input": original_call["function"]["arguments"]},
        },
    }
    assert hosted.canonical_messages(normalized) == hosted.canonical_messages(messages)


def test_hosted_provenance_matches_transcript_service_envelope():
    expected = {
        "case-one": {
            "item": {"case_id": "case-one", "evaluation_response": "Actual generated answer"},
            "sample": {"output_text": "Actual generated answer"},
        }
    }
    output = {
        "datasource_item": {"input": {}, "conversation_id": "row-0"},
        "sample": {
            "input": [
                {
                    **expected["case-one"]["item"],
                    "sample": expected["case-one"]["sample"],
                    "conversation_id": "row-0",
                }
            ]
        },
    }
    assert hosted.matched_source_row(output, expected) == "case-one"


def test_reviewed_evaluators_have_portable_sources_and_exact_dimensions():
    reviewed = assets._assets()
    assert [(asset.name, asset.version, len(asset.dimensions)) for asset in reviewed] == [
        ("hotel-agent-rubric", "8", 15),
        ("hotel-core-quality", "4", 11),
        ("language-continuity", "2", 2),
        ("temporal-boundary", "2", 3),
        ("mail-recipient-integrity", "3", 5),
    ]
    assert all(asset.source_path.is_file() for asset in reviewed)
    assert all(".agent_configs" not in str(asset.source_path) for asset in reviewed)
    assert (
        next(asset for asset in reviewed if asset.name == "hotel-core-quality").pass_threshold
        == 0.5
    )
    for asset in reviewed:
        definition = {
            "dimensions": asset.dimensions,
            "pass_threshold": asset.pass_threshold or 0.8,
        }
        assets._verify_evaluator(
            asset, SimpleNamespace(as_dict=lambda current=definition: {"definition": current})
        )


@pytest.mark.parametrize(
    ("suite", "expected_rows", "query_field"),
    [("quality", 21, "input"), ("full", 27, "query"), ("temporal", 3, "query")],
)
def test_source_suite_bindings(suite, expected_rows, query_field):
    config = quality._suite_config(suite)
    path = config["dataset_path"]
    files = sorted(path.glob("*.jsonl")) if path.is_dir() else [path]
    rows = [json.loads(line) for file in files for line in file.read_text().splitlines() if line]
    assert len(rows) == expected_rows
    assert all(query_field in row for row in rows)
    assert config["query_field"] == query_field
    assert "temporal-boundary" in {name for name, _ in config["evaluators"]}
    assert quality._criterion("language-continuity", "2", query_field)["data_mapping"]["query"] == (
        "{{item." + query_field + "}}"
    )


def test_arabic_family_reservation_matches_authoritative_future_contract():
    rows = multilingual._multilingual_rows()
    arabic = next(row for row in rows if row["id"] == 17)
    assert "September 10 through September 12, 2026" in arabic["description"]
    assert "HTL-004" in arabic["description"]
    assert "10 إلى 12 سبتمبر 2026" in arabic["candidate_response"]
    assert "مستقبلية" in arabic["candidate_response"]
    root = quality._suite_config("quality")["dataset_path"]
    root_rows = [json.loads(line) for line in root.read_text().splitlines()]
    expectation = next(
        row["expected_output"] for row in root_rows if row["input"] == arabic["query"]
    )
    assert "10 إلى 12 سبتمبر 2026" in expectation
    assert "مستقبلية" in expectation
    assert "أغسطس" not in expectation


def test_dual_score_entries_are_not_false_failures():
    result = quality._failure_clusters(
        [
            {
                "results": [
                    {
                        "name": "language-continuity",
                        "metric": "custom_score",
                        "score": 1,
                        "passed": None,
                    },
                    {
                        "name": "language-continuity",
                        "metric": "language-continuity",
                        "passed": True,
                    },
                ],
            }
        ]
    )
    assert result == []
    assert (
        quality._failure_clusters(
            [
                {
                    "results": [
                        {
                            "name": "language-continuity",
                            "metric": "language-continuity",
                            "passed": None,
                        }
                    ]
                }
            ]
        )[0]["count"]
        == 1
    )


def test_context_uses_selected_azd_values_without_source_metadata():
    args = SimpleNamespace(
        environment="hotel-current",
        project_endpoint=None,
        tenant_id=None,
        agent_name=None,
        agent_version=None,
        metadata_file=None,
    )
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(
            quality,
            "_read_azd_environment",
            return_value={
                "AZURE_AI_PROJECT_ENDPOINT": "https://hotel.example/api/projects/hotel",
                "AZURE_TENANT_ID": "target-tenant",
                "AGENT_HOTEL_SERVICING_AGENT_VERSION": "42",
            },
        ),
    ):
        context = quality._resolve_context(args)
    assert context["agent_version"] == "42"
    assert context["metadata_path"].name == "agent-metadata.hotel-current.yaml"
    assert context["environment"] == "hotel-current"


def test_definition_reuse_rejects_changed_query_mapping():
    criterion = quality._criterion("language-continuity", "2", "input")
    remote = SimpleNamespace(
        name="hotel-quality",
        testing_criteria=[SimpleNamespace(model_dump=lambda **kwargs: criterion)],
        data_source_config=SimpleNamespace(
            item_schema={"properties": {"input": {"type": "string"}}, "required": ["input"]}
        ),
    )
    client = SimpleNamespace(evals=SimpleNamespace(retrieve=lambda evaluation_id: remote))
    with patch.object(quality, "_lookup_definition_id", return_value="known-hotel-eval"):
        assert (
            quality._get_or_create_evaluation(
                client, "hotel-quality", (("language-continuity", "2"),), "input"
            )
            is remote
        )
        with pytest.raises(RuntimeError, match="different evaluator bindings"):
            quality._get_or_create_evaluation(
                client, "hotel-quality", (("language-continuity", "2"),), "query"
            )


def test_created_definition_uses_sdk_item_schema():
    client = SimpleNamespace(evals=SimpleNamespace(create=lambda **kwargs: kwargs))
    definition = quality._get_or_create_evaluation(
        client, "hotel-quality", (("language-continuity", "2"),), "input"
    )
    assert definition["data_source_config"]["item_schema"]["required"] == ["input"]
    assert "schema" not in definition["data_source_config"]


def test_definition_reuse_rejects_incomplete_schema():
    criterion = quality._criterion("language-continuity", "2", "input")
    remote = SimpleNamespace(
        name="hotel-quality",
        testing_criteria=[SimpleNamespace(model_dump=lambda **kwargs: criterion)],
        data_source_config=SimpleNamespace(item_schema={}),
    )
    client = SimpleNamespace(evals=SimpleNamespace(retrieve=lambda evaluation_id: remote))
    with (
        patch.object(quality, "_lookup_definition_id", return_value="known-hotel-eval"),
        pytest.raises(RuntimeError, match="incomplete item_schema"),
    ):
        quality._get_or_create_evaluation(
            client, "hotel-quality", (("language-continuity", "2"),), "input"
        )


def test_validation_subset_preserves_reviewed_rows():
    rows = multilingual._multilingual_rows()
    content = multilingual._validation_content(rows)
    assert [row["source_case_id"] for row in content] == [16, 17, 18]
    for source, selected in zip(rows, content, strict=True):
        assert selected["query"] == source["query"]
        assert selected["response"] == source["candidate_response"]
        assert set(selected) == {"source_case_id", "query", "response"}


def test_static_definition_uses_sdk_item_schema():
    client = SimpleNamespace(evals=SimpleNamespace(create=lambda **kwargs: kwargs))
    definition = multilingual._get_or_create_eval(client)
    schema = definition["data_source_config"]["item_schema"]
    assert set(schema["required"]) == {"query", "response"}
    assert set(schema["properties"]) == set(schema["required"])
    assert "schema" not in definition["data_source_config"]


def test_static_definition_rejects_incomplete_schema():
    criterion = SimpleNamespace(
        evaluator_name="language-continuity",
        evaluator_version="2",
        initialization_parameters={"model": "gpt-5.4-mini"},
        data_mapping={
            "query": "{{item.query}}",
            "response": "{{item.response}}",
        },
    )
    remote = SimpleNamespace(
        name=multilingual.EVAL_NAME,
        testing_criteria=[criterion],
        data_source_config=SimpleNamespace(item_schema={}),
    )
    client = SimpleNamespace(evals=SimpleNamespace(retrieve=lambda evaluation_id: remote))
    with (
        patch.object(multilingual, "_lookup_definition_id", return_value="known-hotel-eval"),
        pytest.raises(RuntimeError, match="incomplete item_schema"),
    ):
        multilingual._get_or_create_eval(client)


@pytest.mark.parametrize("properties", [{}, {"query": {"type": "string"}}])
def test_readback_uses_response_schema_namespace(properties):
    schema = {"type": "object", "properties": properties, "required": ["query"]}
    definition = SimpleNamespace(
        data_source_config=SimpleNamespace(item_schema={}, schema_={"item": schema})
    )
    assert quality._evaluation_item_schema(definition) == schema


def test_failure_cluster_keeps_service_error_message():
    items = [
        {
            "results": [
                {
                    "name": "language-continuity",
                    "passed": None,
                    "sample": {"error": {"message": "Missing evaluation_query input"}},
                }
            ]
        }
    ]
    assert quality._failure_clusters(items)[0]["reasons"] == ["Missing evaluation_query input"]


@pytest.mark.parametrize(
    "language_fields",
    [("query", "response"), ("evaluation_query", "evaluation_response")],
)
def test_publication_verifies_current_static_language_schema(language_fields):
    definitions = {}

    def definition(name, fields):
        schema = {
            "type": "object",
            "properties": {field: {"type": "string"} for field in fields},
            "required": list(fields),
        }
        result = SimpleNamespace(
            id=name,
            name=name,
            data_source_config=SimpleNamespace(item_schema=schema),
            model_dump=lambda **kwargs: {"name": name},
        )
        definitions[name] = result
        return result

    def quality_definition(client, name, evaluators, query_field, *args):
        return definition(name, (query_field,))

    language = definition(multilingual.EVAL_NAME, language_fields)
    openai_client = SimpleNamespace(
        evals=SimpleNamespace(retrieve=lambda identifier: definitions[identifier])
    )
    client = SimpleNamespace(
        get_openai_client=lambda: nullcontext(openai_client),
        datasets=SimpleNamespace(
            get=lambda name, version: SimpleNamespace(
                name=name, version=version, id=f"dataset:{name}:{version}", data_uri="storage"
            )
        ),
        beta=SimpleNamespace(evaluators=SimpleNamespace(get_version=lambda name, version: None)),
    )
    with (
        patch.object(assets, "_assets", return_value=[]),
        patch.object(assets, "_get_or_create_evaluation", side_effect=quality_definition),
        patch.object(assets, "_get_or_create_eval", return_value=language),
    ):
        if language_fields != ("query", "response"):
            with pytest.raises(RuntimeError, match="incomplete item_schema"):
                assets._ensure_definitions(client, None)
        else:
            results = assets._ensure_definitions(client, None)
            assert len(results) == 4
            assert results[-1]["itemSchema"]["required"] == ["query", "response"]
            assert results[-1]["agentInvoked"] is False
