from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

EXPECTED_AGENT_NAME = "hotel-servicing-agent"
EXPECTED_MODEL = "gpt-5.4-mini"
EXPECTED_KNOWLEDGE_BASE = "hotel-foundryiq"
AGENT365_DEPLOYMENT_ENV = (
    "AGENT365_TENANT_ID",
    "AGENT365_BLUEPRINT_CLIENT_ID",
    "AGENT365_BLUEPRINT_SECRET_VAULT_URL",
    "AGENT365_INSTANCE_CLIENT_ID",
)
EXPECTED_AGENT365_ENV = {
    "AGENT365_BLUEPRINT_SECRET_NAME": "agent365-blueprint-client-secret",
    "WORK_IQ_COPILOT_MCP_URL": (
        "https://agent365.svc.cloud.microsoft/agents/servers/mcp_M365Copilot"
    ),
    "WORK_IQ_COPILOT_MCP_AUDIENCE": "ab7c82de-7946-4454-ac28-70249d17c95e",
    "WORK_IQ_MAIL_MCP_URL": "https://agent365.svc.cloud.microsoft/agents/servers/mcp_MailTools",
    "WORK_IQ_MAIL_MCP_AUDIENCE": "16b1878d-62c7-4009-aa25-68989d63bbad",
    "WORK_IQ_TEAMS_MCP_URL": (
        "https://agent365.svc.cloud.microsoft/agents/servers/mcp_TeamsServer"
    ),
    "WORK_IQ_TEAMS_MCP_AUDIENCE": "ce5029ee-c1d3-45c0-bdcc-efb5a4245687",
}
EXPECTED_OBSERVABILITY_ENV = {"A365_USE_S2S_ENDPOINT": "true"}
SHARED_DEPLOYMENT_ENV = (
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "VOICE_LIVE_ENDPOINT",
    "VOICE_LIVE_VOICE",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_OPENAI_ENDPOINT",
    "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
    "FABRIC_DATA_AGENT_MCP_URL",
    "FABRIC_WORKSPACE_ID",
    "FABRIC_GUEST_SERVICES_LAKEHOUSE_ID",
    "FABRIC_RESERVATION_NOTEBOOK_ID",
    "AZURE_STORAGE_ACCOUNT_URL",
    "FOUNDRY_IQ_BLOB_CONTAINER",
    *AGENT365_DEPLOYMENT_ENV,
    *EXPECTED_AGENT365_ENV,
)
EXPECTED_PROTOCOLS = [
    {"protocol": "responses", "version": "2.0.0"},
    {"protocol": "invocations_ws", "version": "1.0.0"},
]
EXPECTED_VOICE_LIVE_ENV = {
    "VOICE_LIVE_ENDPOINT": "${VOICE_LIVE_ENDPOINT}",
    "VOICE_LIVE_API_VERSION": "2026-04-10",
    "VOICE_LIVE_AGENT_NAME": EXPECTED_AGENT_NAME,
    "VOICE_LIVE_PROJECT_NAME": "${AZURE_AI_PROJECT_NAME}",
    "VOICE_LIVE_VOICE": "${VOICE_LIVE_VOICE}",
}
EXPECTED_MANIFEST_VOICE_LIVE_ENV = {
    "VOICE_LIVE_ENDPOINT": "{{VOICE_LIVE_ENDPOINT}}",
    "VOICE_LIVE_API_VERSION": "2026-04-10",
    "VOICE_LIVE_AGENT_NAME": EXPECTED_AGENT_NAME,
    "VOICE_LIVE_PROJECT_NAME": "{{AZURE_AI_PROJECT_NAME}}",
    "VOICE_LIVE_VOICE": "{{VOICE_LIVE_VOICE}}",
}


@dataclass(frozen=True, slots=True)
class ConfigurationProblem:
    field: str
    message: str


def validate_repository_configuration(root: Path) -> list[ConfigurationProblem]:
    azure = _load_yaml(root / "azure.yaml")
    manifest = _load_yaml(root / "src/hotel-servicing-agent/agent.manifest.yaml")
    tooling_manifest = _load_json(root / "agent/ToolingManifest.json")
    m365_manifest = _load_json(root / "manifest/manifest.json")
    agentic_user_template = _load_json(root / "manifest/agenticUserTemplateManifest.json")
    evaluation = _load_yaml(root / "eval.yaml")
    env = _load_env(root / "config/azd.env.example")
    local_env = _load_env(root / ".env.template")
    problems: list[ConfigurationProblem] = []

    services = _mapping(azure.get("services"))
    infrastructure = _mapping(azure.get("infra"))
    project = _mapping(services.get("ai-project"))
    agent = _mapping(services.get(EXPECTED_AGENT_NAME))
    template = _mapping(manifest.get("template"))
    environment_variables = _named_values(agent.get("environmentVariables"))

    _expect(problems, "azure.name", azure.get("name"), "hotel-agent-a365")
    _expect(problems, "infra.provider", infrastructure.get("provider"), "microsoft.foundry")
    _expect(problems, "services.ai-project.host", project.get("host"), "azure.ai.project")
    deployments = project.get("deployments")
    _expect(
        problems,
        "services.ai-project.deployments.count",
        len(deployments) if isinstance(deployments, list) else 0,
        1,
    )
    _expect(
        problems,
        "services.ai-project.deployments[0].name",
        _nested_sequence(project, "deployments", 0, "name"),
        EXPECTED_MODEL,
    )
    _expect(problems, "agent.host", agent.get("host"), "azure.ai.agent")
    _expect(problems, "agent.kind", agent.get("kind"), "hosted")
    _expect(problems, "agent.name", agent.get("name"), EXPECTED_AGENT_NAME)
    _expect(problems, "agent.project", agent.get("project"), "src/hotel-servicing-agent")
    _expect(problems, "agent.language", agent.get("language"), "python")
    _expect(problems, "agent.protocols", agent.get("protocols"), EXPECTED_PROTOCOLS)
    _expect(
        problems,
        "agent.codeConfiguration.runtime",
        _nested(agent, "codeConfiguration", "runtime"),
        "python_3_13",
    )
    _expect(
        problems,
        "agent.codeConfiguration.entryPoint",
        _nested(agent, "codeConfiguration", "entryPoint"),
        "main.py",
    )
    _expect(
        problems,
        "agent.codeConfiguration.dependencyResolution",
        _nested(agent, "codeConfiguration", "dependencyResolution"),
        "remote_build",
    )
    _expect(
        problems,
        "agent.container.resources.cpu",
        _nested(agent, "container", "resources", "cpu"),
        "1",
    )
    _expect(
        problems,
        "agent.container.resources.memory",
        _nested(agent, "container", "resources", "memory"),
        "2Gi",
    )
    _expect(
        problems,
        "agent.environmentVariables.AZURE_AI_MODEL_DEPLOYMENT_NAME",
        environment_variables.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        "${AZURE_AI_MODEL_DEPLOYMENT_NAME}",
    )
    _expect(
        problems,
        "agent.environmentVariables.AZURE_SEARCH_ENDPOINT",
        environment_variables.get("AZURE_SEARCH_ENDPOINT"),
        "${AZURE_SEARCH_ENDPOINT}",
    )
    _expect(
        problems,
        "agent.environmentVariables.FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
        environment_variables.get("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"),
        "${FOUNDRY_IQ_KNOWLEDGE_BASE_NAME}",
    )
    _expect(
        problems,
        "agent.environmentVariables.FABRIC_DATA_AGENT_MCP_URL",
        environment_variables.get("FABRIC_DATA_AGENT_MCP_URL"),
        "${FABRIC_DATA_AGENT_MCP_URL}",
    )
    for name in (*AGENT365_DEPLOYMENT_ENV, *EXPECTED_AGENT365_ENV):
        _expect(
            problems,
            f"agent.environmentVariables.{name}",
            environment_variables.get(name),
            f"${{{name}}}",
        )
    for name, expected in EXPECTED_OBSERVABILITY_ENV.items():
        _expect(
            problems,
            f"agent.environmentVariables.{name}",
            environment_variables.get(name),
            expected,
        )
    for name, expected in EXPECTED_VOICE_LIVE_ENV.items():
        _expect(
            problems,
            f"agent.environmentVariables.{name}",
            environment_variables.get(name),
            expected,
        )
    _expect(
        problems,
        "agent.environmentVariables.FOUNDRY_PROJECT_ENDPOINT",
        environment_variables.get("FOUNDRY_PROJECT_ENDPOINT"),
        "${FOUNDRY_PROJECT_ENDPOINT}",
    )

    _expect(problems, "manifest.template.name", template.get("name"), EXPECTED_AGENT_NAME)
    _expect(problems, "manifest.template.kind", template.get("kind"), "hosted")
    _expect(
        problems,
        "manifest.template.protocols",
        template.get("protocols"),
        EXPECTED_PROTOCOLS,
    )
    manifest_environment_variables = _named_values(template.get("environment_variables"))
    for name in (
        "FOUNDRY_PROJECT_ENDPOINT",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        "AZURE_SEARCH_ENDPOINT",
        "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
        "FABRIC_DATA_AGENT_MCP_URL",
        *AGENT365_DEPLOYMENT_ENV,
        *EXPECTED_AGENT365_ENV,
        *EXPECTED_OBSERVABILITY_ENV,
    ):
        expected = EXPECTED_OBSERVABILITY_ENV.get(name, f"{{{{{name}}}}}")
        _expect(
            problems,
            f"manifest.template.environment_variables.{name}",
            manifest_environment_variables.get(name),
            expected,
        )
    for name, expected in EXPECTED_MANIFEST_VOICE_LIVE_ENV.items():
        _expect(
            problems,
            f"manifest.template.environment_variables.{name}",
            manifest_environment_variables.get(name),
            expected,
        )
    _expect(
        problems,
        "manifest.template.environment_variables.AGENT_INSTRUCTIONS_PATH",
        manifest_environment_variables.get("AGENT_INSTRUCTIONS_PATH"),
        "agent-instructions.md",
    )
    _expect(
        problems,
        "manifest.model.id",
        _nested_sequence(manifest, "resources", 0, "id"),
        EXPECTED_MODEL,
    )

    _expect(
        problems,
        "AZURE_AI_PROJECT_ENDPOINT",
        env.get("AZURE_AI_PROJECT_ENDPOINT"),
        env.get("FOUNDRY_PROJECT_ENDPOINT"),
    )
    _expect(
        problems,
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        env.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        EXPECTED_MODEL,
    )
    _expect(
        problems,
        "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
        env.get("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"),
        EXPECTED_KNOWLEDGE_BASE,
    )
    for name in SHARED_DEPLOYMENT_ENV:
        if name not in env:
            problems.append(ConfigurationProblem(name, "required environment binding is missing"))
        _expect(problems, f".env.{name}", local_env.get(name), env.get(name))
    for name, expected in EXPECTED_AGENT365_ENV.items():
        _expect(problems, name, env.get(name), expected)
    _expect(
        problems,
        "ToolingManifest.mcpServers",
        tooling_manifest.get("mcpServers"),
        [
            {
                "mcpServerName": "work-iq-copilot",
                "mcpServerUniqueName": "mcp_M365Copilot",
                "url": EXPECTED_AGENT365_ENV["WORK_IQ_COPILOT_MCP_URL"],
                "scope": "Tools.ListInvoke.All",
                "audience": EXPECTED_AGENT365_ENV["WORK_IQ_COPILOT_MCP_AUDIENCE"],
            },
            {
                "mcpServerName": "work-iq-mail",
                "mcpServerUniqueName": "mcp_MailTools",
                "url": EXPECTED_AGENT365_ENV["WORK_IQ_MAIL_MCP_URL"],
                "scope": "Tools.ListInvoke.All",
                "audience": EXPECTED_AGENT365_ENV["WORK_IQ_MAIL_MCP_AUDIENCE"],
            },
            {
                "mcpServerName": "work-iq-teams",
                "mcpServerUniqueName": "mcp_TeamsServer",
                "url": EXPECTED_AGENT365_ENV["WORK_IQ_TEAMS_MCP_URL"],
                "scope": "Tools.ListInvoke.All",
                "audience": EXPECTED_AGENT365_ENV["WORK_IQ_TEAMS_MCP_AUDIENCE"],
            },
        ],
    )
    blueprint_id = m365_manifest.get("id")
    template_id = agentic_user_template.get("id")
    _expect_uuid(problems, "m365.manifest.id", blueprint_id)
    _expect_uuid(problems, "m365.agenticUserTemplate.id", template_id)
    if env.get("AGENT365_BLUEPRINT_CLIENT_ID"):
        _expect(
            problems,
            "m365.manifest.id",
            blueprint_id,
            env["AGENT365_BLUEPRINT_CLIENT_ID"],
        )
    _expect(
        problems,
        "m365.manifest.agenticUserTemplates[0].id",
        _nested_sequence(m365_manifest, "agenticUserTemplates", 0, "id"),
        template_id,
    )
    _expect(
        problems,
        "m365.manifest.agenticUserTemplates[0].file",
        _nested_sequence(m365_manifest, "agenticUserTemplates", 0, "file"),
        "agenticUserTemplateManifest.json",
    )
    _expect(
        problems,
        "m365.agenticUserTemplate.agentIdentityBlueprintId",
        agentic_user_template.get("agentIdentityBlueprintId"),
        blueprint_id,
    )
    _expect(
        problems,
        "m365.agenticUserTemplate.communicationProtocol",
        agentic_user_template.get("communicationProtocol"),
        "activityProtocol",
    )
    for icon in ("color.png", "outline.png"):
        if not (root / "manifest" / icon).is_file():
            problems.append(
                ConfigurationProblem(
                    f"m365.manifest.icons.{icon}",
                    f"required package icon is missing: manifest/{icon}",
                )
            )
    evaluation_dataset = _nested(evaluation, "dataset", "local_uri")
    if not isinstance(evaluation_dataset, str) or not (root / evaluation_dataset).is_file():
        problems.append(
            ConfigurationProblem(
                "eval.dataset.local_uri",
                f"dataset file does not exist: {evaluation_dataset!r}",
            )
        )
    deployed_instructions = root / "src/hotel-servicing-agent/agent-instructions.md"
    root_instructions = root / "agent-instructions.md"
    if deployed_instructions.read_bytes() != root_instructions.read_bytes():
        problems.append(
            ConfigurationProblem(
                "agent.instructions",
                "root and deployed agent instruction files must stay identical",
            )
        )
    return problems


def _expect(
    problems: list[ConfigurationProblem],
    field: str,
    actual: object,
    expected: object,
) -> None:
    if actual != expected:
        problems.append(ConfigurationProblem(field, f"expected {expected!r}, found {actual!r}"))


def _expect_uuid(problems: list[ConfigurationProblem], field: str, value: object) -> None:
    try:
        parsed = UUID(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.int == 0:
        problems.append(ConfigurationProblem(field, f"expected a nonzero UUID, found {value!r}"))


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _mapping(value)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _mapping(value)


def _load_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            raise ValueError(f"Invalid environment template line: {line}")
        result[key] = value
    return result


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _named_values(value: object) -> dict[str, object]:
    if not isinstance(value, list):
        return {}
    return {
        item["name"]: item.get("value")
        for item in value
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def _nested(value: dict[str, Any], *keys: str) -> object:
    current: object = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _nested_sequence(
    value: dict[str, Any],
    sequence_key: str,
    index: int,
    child_key: str,
) -> object:
    sequence = value.get(sequence_key)
    if not isinstance(sequence, list) or len(sequence) <= index:
        return None
    child = sequence[index]
    return child.get(child_key) if isinstance(child, dict) else None
