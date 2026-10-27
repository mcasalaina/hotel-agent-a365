from __future__ import annotations

import json
from pathlib import Path
from shutil import copyfile

import yaml
from repo_validation.configuration import (
    EXPECTED_AGENT_NAME,
    EXPECTED_MODEL,
    validate_repository_configuration,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_bootstrap_configuration_is_consistent() -> None:
    assert validate_repository_configuration(REPOSITORY_ROOT) == []


def test_expected_generic_agent_and_model_names() -> None:
    assert EXPECTED_AGENT_NAME == "hotel-servicing-agent"
    assert EXPECTED_MODEL == "gpt-5.4-mini"


def _copy_configuration(destination: Path) -> Path:
    paths = [
        "azure.yaml",
        "src/hotel-servicing-agent/agent.manifest.yaml",
        "agent/ToolingManifest.json",
        "manifest/manifest.json",
        "manifest/agenticUserTemplateManifest.json",
        "manifest/color.png",
        "manifest/outline.png",
        "eval.yaml",
        "config/azd.env.example",
        ".env.template",
        "agent-instructions.md",
        "src/hotel-servicing-agent/agent-instructions.md",
    ]
    evaluation = yaml.safe_load((REPOSITORY_ROOT / "eval.yaml").read_text())
    paths.append(evaluation["dataset"]["local_uri"])
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copyfile(REPOSITORY_ROOT / relative, target)
    return destination


def test_configuration_can_bind_to_another_tenant(tmp_path: Path) -> None:
    root = _copy_configuration(tmp_path)
    blueprint = "11111111-2222-4333-8444-555555555555"
    instance = "22222222-3333-4444-8555-666666666666"
    for relative in ("config/azd.env.example", ".env.template"):
        path = root / relative
        lines = []
        for line in path.read_text().splitlines():
            if line.startswith("AGENT365_BLUEPRINT_CLIENT_ID="):
                line = f"AGENT365_BLUEPRINT_CLIENT_ID={blueprint}"
            elif line.startswith("AGENT365_INSTANCE_CLIENT_ID="):
                line = f"AGENT365_INSTANCE_CLIENT_ID={instance}"
            lines.append(line.replace("mcasalaina-4iqs-2701", "hotel-alternate"))
        path.write_text("\n".join(lines) + "\n")
    manifest_path = root / "manifest/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["id"] = blueprint
    manifest_path.write_text(json.dumps(manifest))
    template_path = root / "manifest/agenticUserTemplateManifest.json"
    template = json.loads(template_path.read_text())
    template["agentIdentityBlueprintId"] = blueprint
    template_path.write_text(json.dumps(template))

    assert validate_repository_configuration(root) == []


def test_configuration_rejects_cross_tenant_local_binding(tmp_path: Path) -> None:
    root = _copy_configuration(tmp_path)
    path = root / ".env.template"
    path.write_text(path.read_text().replace("2701-search", "other-search"))

    fields = {problem.field for problem in validate_repository_configuration(root)}
    assert ".env.AZURE_SEARCH_ENDPOINT" in fields


def test_configuration_rejects_mismatched_blueprint(tmp_path: Path) -> None:
    root = _copy_configuration(tmp_path)
    path = root / "manifest/agenticUserTemplateManifest.json"
    template = json.loads(path.read_text())
    template["agentIdentityBlueprintId"] = "33333333-4444-4555-8666-777777777777"
    path.write_text(json.dumps(template))

    fields = {problem.field for problem in validate_repository_configuration(root)}
    assert "m365.agenticUserTemplate.agentIdentityBlueprintId" in fields


def test_configuration_rejects_additional_model_deployment(tmp_path: Path) -> None:
    root = _copy_configuration(tmp_path)
    path = root / "azure.yaml"
    azure = yaml.safe_load(path.read_text())
    azure["services"]["ai-project"]["deployments"].append({"name": "text-embedding-3-small"})
    path.write_text(yaml.safe_dump(azure))

    fields = {problem.field for problem in validate_repository_configuration(root)}
    assert "services.ai-project.deployments.count" in fields


def test_configuration_requires_explicit_project_binding(tmp_path: Path) -> None:
    root = _copy_configuration(tmp_path)
    path = root / "azure.yaml"
    azure = yaml.safe_load(path.read_text())
    agent = azure["services"]["hotel-servicing-agent"]
    agent["environmentVariables"] = [
        item for item in agent["environmentVariables"] if item["name"] != "FOUNDRY_PROJECT_ENDPOINT"
    ]
    path.write_text(yaml.safe_dump(azure))

    fields = {problem.field for problem in validate_repository_configuration(root)}
    assert "agent.environmentVariables.FOUNDRY_PROJECT_ENDPOINT" in fields
