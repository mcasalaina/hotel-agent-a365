from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from deploy_semantic_model_and_report import (
    FABRIC_API,
    ROOT,
    AzRest,
    build_definition,
    deploy_item,
    refresh_and_validate,
    source_readiness,
    verify_definitions,
)

VALUES = {
    "WORKSPACE_ID": "workspace-id",
    "HOTEL_GUEST_SERVICES_LAKEHOUSE_ID": "guest-id",
    "HOTEL_OPERATIONS_LAKEHOUSE_ID": "ops-id",
    "SEMANTICMODEL_ID": "model-id",
}


def decode(definition: dict) -> dict[str, str]:
    return {
        part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
        for part in definition["parts"]
    }


def test_committed_definitions_are_complete_and_externalized() -> None:
    model = decode(build_definition(ROOT / "fabric/semantic-model", VALUES))
    report = decode(build_definition(ROOT / "fabric/report", VALUES))
    assert len(model) == 13
    assert "blueprint.json" not in model
    assert "README.md" not in model
    assert ".platform" not in model
    assert model["definition.pbism"].encode("utf-8") == (
        ROOT / "fabric/semantic-model/definition.pbism"
    ).read_bytes()
    assert "workspace-id/guest-id" in model["definition/model.tmdl"]
    assert "workspace-id/ops-id" in model["definition/model.tmdl"]
    assert not any("{{" in text for text in [*model.values(), *report.values()])
    assert json.loads(report["definition.pbir"])["datasetReference"]["byConnection"] == {
        "connectionString": "semanticmodelid=model-id"
    }
    assert sum(path.endswith("/page.json") for path in report) == 6
    assert sum(path.endswith("/visual.json") for path in report) == 19


@pytest.mark.parametrize("qna_enabled", [False, True])
def test_builder_preserves_selected_template_settings_byte_for_byte(
    qna_enabled: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = Mock(side_effect=AssertionError("Template builds must remain local"))
    monkeypatch.setattr(subprocess, "run", command)
    (tmp_path / "blueprint.json").write_text(
        json.dumps({"definitionFormat": "TMDL", "includePaths": ["definition.pbism"]}),
        encoding="utf-8",
    )
    # Deliberately noncanonical formatting and an unknown setting must pass through,
    # regardless of the user's chosen Q&A setting. This is not an AI configuration.
    source = (
        json.dumps(
            {
                "version": "5.0",
                "settings": {
                    "qnaEnabled": qna_enabled,
                    "unknownSetting": {"marker": "retain café", "values": [3, 1, 2]},
                },
            },
            ensure_ascii=False,
            indent=3,
        )
        + "\n\n"
    ).encode("utf-8")
    template = tmp_path / "definition.pbism"
    template.write_bytes(source)
    definition = build_definition(tmp_path, {})
    assert definition["format"] == "TMDL"
    assert len(definition["parts"]) == 1
    part = definition["parts"][0]
    assert part["path"] == "definition.pbism"
    assert part["payloadType"] == "InlineBase64"
    actual = base64.b64decode(part["payload"])
    assert actual == source
    assert json.loads(actual)["settings"]["qnaEnabled"] is qna_enabled
    assert template.read_bytes() == source
    command.assert_not_called()


def test_missing_environment_binding_fails_before_deployment() -> None:
    with pytest.raises(ValueError, match="Missing template values"):
        build_definition(ROOT / "fabric/semantic-model", {})


def test_requests_cannot_access_another_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    run = Mock()
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError, match="outside the selected workspace"):
        AzRest("hotel").request("GET", FABRIC_API + "/workspaces/another/items")
    with pytest.raises(ValueError, match="outside the selected workspace"):
        AzRest("hotel").request("GET", FABRIC_API + "/connections")
    run.assert_not_called()


@pytest.mark.parametrize(
    "skill", ["semantic-model-authoring", "spark-cli", "fabriciq-ontology-cli"]
)
def test_lro_poll_and_result_keep_skill_header(monkeypatch: pytest.MonkeyPatch, skill: str) -> None:
    responses = [
        subprocess.CompletedProcess(
            [],
            0,
            "",
            "INFO: Response status: 202\n"
            "INFO:     'Location': 'https://api.fabric.microsoft.com/v1/operations/operation'\n"
            "INFO:     'Retry-After': '1'\n",
        ),
        subprocess.CompletedProcess(
            [], 0, '{"status":"Succeeded"}', "INFO: Response status: 200\n"
        ),
        subprocess.CompletedProcess([], 0, '{"id":"model"}', "INFO: Response status: 200\n"),
    ]
    run = Mock(side_effect=responses)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("deploy_semantic_model_and_report.time.sleep", lambda _: None)
    assert AzRest("hotel", skill=skill).request(
        "POST", FABRIC_API + "/workspaces/hotel/items", {}
    ) == {"id": "model"}
    assert len(run.call_args_list) == 3
    for call in run.call_args_list:
        assert f"x-ms-fabric-skill={skill}" in call.args[0]
        assert "--resource" in call.args[0]


def test_regional_lro_location_uses_canonical_fabric_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = "8d457d09-2b90-4a2e-a03c-eff55da0fd01"
    run = Mock(
        side_effect=[
            subprocess.CompletedProcess(
                [],
                0,
                "",
                "INFO: Response status: 202\n"
                "INFO:     'Location': "
                f"'https://wabi-us-central-b-primary-redirect.analysis.windows.net/v1/operations/{operation}'\n",
            ),
            subprocess.CompletedProcess(
                [], 0, '{"status":"Succeeded"}', "INFO: Response status: 200\n"
            ),
        ]
    )
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("deploy_semantic_model_and_report.time.sleep", lambda _: None)
    AzRest("hotel").request("POST", FABRIC_API + "/workspaces/hotel/items", {}, result=False)
    assert FABRIC_API + "/operations/" + operation in run.call_args.args[0]


def test_duplicate_names_fail_without_writes() -> None:
    client = Mock()
    client.items.return_value = [
        {"id": "one", "displayName": "HotelOperationsModel"},
        {"id": "two", "displayName": "HotelOperationsModel"},
    ]
    with pytest.raises(RuntimeError, match="Multiple SemanticModel"):
        deploy_item(client, ROOT / "fabric/semantic-model", VALUES)
    client.request.assert_not_called()


def test_existing_model_replacement_fails_closed_before_build_or_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = Mock(workspace_id="hotel")
    item = {"id": "model", "displayName": "HotelOperationsModel"}
    client.items.return_value = [item]
    build = Mock(side_effect=AssertionError("Existing model must not be rebuilt"))
    monkeypatch.setattr("deploy_semantic_model_and_report.build_definition", build)
    with pytest.raises(RuntimeError, match="cannot guarantee preservation") as error:
        # Missing values cannot bypass the preservation guard or mask its diagnostic.
        deploy_item(client, ROOT / "fabric/semantic-model", {})
    assert "model" in str(error.value)
    assert "workspace hotel" in str(error.value)
    assert "field-level TOM" in str(error.value)
    assert "Prep for AI" in str(error.value)
    assert "Do not delete/recreate" in str(error.value)
    build.assert_not_called()
    # In particular: no getDefinition, updateDefinition, PATCH, create or delete.
    client.request.assert_not_called()


@pytest.mark.parametrize("export_shape", ["identical", "unknown-part", "embedded-metadata"])
def test_an_export_cannot_bypass_existing_model_preservation_guard(export_shape: str) -> None:
    client = Mock(workspace_id="hotel")
    client.items.return_value = [{"id": "model", "displayName": "HotelOperationsModel"}]
    definition = build_definition(ROOT / "fabric/semantic-model", VALUES)
    if export_shape == "unknown-part":
        definition["parts"].append(
            {"path": "unknown.bin", "payload": "AP8NCg==", "payloadType": "InlineBase64"}
        )
    elif export_shape == "embedded-metadata":
        part = definition["parts"][0]
        original = base64.b64decode(part["payload"])
        part["payload"] = base64.b64encode(original + b"\nopaque-marker\r\n").decode()
    exported = {"definition": definition}
    before = json.dumps(exported, sort_keys=True)
    client.request.return_value = exported
    with pytest.raises(RuntimeError, match="Refusing updateDefinition"):
        deploy_item(client, ROOT / "fabric/semantic-model", VALUES)
    assert json.dumps(exported, sort_keys=True) == before
    client.request.assert_not_called()


def test_new_model_creation_still_uses_complete_parameterized_definition() -> None:
    client = Mock(workspace_id="hotel")
    item = {"id": "new-model", "displayName": "HotelOperationsModel"}
    client.items.side_effect = [[], [item]]
    client.request.return_value = item
    assert deploy_item(client, ROOT / "fabric/semantic-model", VALUES) == item
    client.request.assert_called_once()
    method, url, body = client.request.call_args.args
    assert method == "POST"
    assert url == FABRIC_API + "/workspaces/hotel/items"
    assert body["type"] == "SemanticModel"
    assert body["definition"] == build_definition(ROOT / "fabric/semantic-model", VALUES)
    assert len(body["definition"]["parts"]) == 13


def test_live_definition_verification_catches_incorrect_report_binding() -> None:
    client = Mock(workspace_id="hotel")
    client.request.side_effect = [
        {"definition": build_definition(ROOT / "fabric/semantic-model", VALUES)},
        {
            "definition": build_definition(
                ROOT / "fabric/report", {**VALUES, "SEMANTICMODEL_ID": "wrong"}
            )
        },
    ]
    with pytest.raises(RuntimeError, match="not bound"):
        verify_definitions(client, "model-id", "report-id", VALUES)


def test_live_definitions_verify_tables_partitions_and_pages() -> None:
    client = Mock(workspace_id="hotel")
    client.request.side_effect = [
        {"definition": build_definition(ROOT / "fabric/semantic-model", VALUES)},
        {"definition": build_definition(ROOT / "fabric/report", VALUES)},
        {"datasetId": "model-id", "datasetWorkspaceId": "hotel"},
    ]
    evidence = verify_definitions(client, "model-id", "report-id", VALUES)
    assert len(evidence["tables"]) == 9
    assert evidence["directLakePartitions"] == 8
    assert len(evidence["reportPages"]) == 6


def test_service_expanded_connection_string_preserves_model_binding() -> None:
    report = build_definition(ROOT / "fabric/report", VALUES)
    for part in report["parts"]:
        if part["path"] == "definition.pbir":
            content = json.loads(base64.b64decode(part["payload"]))
            content["datasetReference"]["byConnection"]["connectionString"] = (
                "Data Source=powerbi://api.powerbi.com/v1.0/myorg/HotelAgent.Workspace;"
                "initial catalog=HotelOperationsModel;integrated security=ClaimsToken;"
                "semanticmodelid=model-id"
            )
            part["payload"] = base64.b64encode(json.dumps(content).encode()).decode()
    client = Mock(workspace_id="hotel")
    client.request.side_effect = [
        {"definition": build_definition(ROOT / "fabric/semantic-model", VALUES)},
        {"definition": report},
        {"datasetId": "model-id", "datasetWorkspaceId": "hotel"},
    ]
    assert (
        verify_definitions(client, "model-id", "report-id", VALUES)["reportDatasetId"] == "model-id"
    )


def test_readiness_lists_missing_delta_tables_without_refreshing() -> None:
    client = Mock(workspace_id="hotel")
    client.request.return_value = {"data": [{"name": "ops_properties"}, {"name": "ops_outlets"}]}
    readiness = source_readiness(client, "guest")
    assert readiness["ready"] is False
    assert len(readiness["missingTables"]) == 6
    assert "agg_property_kpis_daily" in readiness["missingTables"]
    assert client.request.call_args.args[0] == "GET"


def test_refresh_credential_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock(workspace_id="hotel", timeout=10)
    client.request.side_effect = [
        {},
        {"value": [{"status": "Failed", "serviceExceptionJson": "CredentialsNotSpecified"}]},
    ]
    monkeypatch.setattr("deploy_semantic_model_and_report.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="was not retried"):
        refresh_and_validate(client, "model")
    assert client.request.call_count == 2


def test_dax_table_errors_fail_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock(workspace_id="hotel", timeout=10)
    client.request.side_effect = [
        {},
        {"value": [{"status": "Completed"}]},
        {"results": [{"tables": [{"error": {"code": "DAXError"}}]}]},
    ]
    monkeypatch.setattr("deploy_semantic_model_and_report.time.sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="DAX validation failed"):
        refresh_and_validate(client, "model")
