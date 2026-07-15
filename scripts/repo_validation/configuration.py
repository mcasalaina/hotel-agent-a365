from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

EXPECTED_AGENT_NAME = "hotel-servicing-agent"
EXPECTED_MODEL = "gpt-5.4-mini"
EXPECTED_AGENT365_BLUEPRINT_ID = "f1ae4991-0418-470b-96d5-7f7df43ab5d2"
EXPECTED_AGENT365_TEMPLATE_ID = "9a2da06d-059c-4b40-910f-ca8e0a6b1730"
EXPECTED_SEARCH_ENDPOINT = "https://3iqs-search-aycabas.search.windows.net"
EXPECTED_KNOWLEDGE_BASE = "hotel-foundryiq"
EXPECTED_FABRIC_DATA_AGENT_MCP_URL = (
    "https://api.fabric.microsoft.com/v1/mcp/workspaces/"
    "660ed238-54b7-42bd-8b1b-cf2ee47a11ba/dataagents/"
    "9990b87a-d2ef-4c23-b11d-ffd72905906c/agent"
)
EXPECTED_AGENT365_ENV = {
    "AGENT365_TENANT_ID": "a9d9510e-7131-4355-8b7e-37e7b1e99862",
    "AGENT365_BLUEPRINT_CLIENT_ID": "f1ae4991-0418-470b-96d5-7f7df43ab5d2",
    "AGENT365_BLUEPRINT_SECRET_VAULT_URL": "https://hotelagentkv4iqs.vault.azure.net",
    "AGENT365_BLUEPRINT_SECRET_NAME": "agent365-blueprint-client-secret",
    "AGENT365_INSTANCE_CLIENT_ID": "cc4f4078-c463-494a-a5fc-0b63a6995296",
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
EXPECTED_PROJECT_ENDPOINT = (
    "https://4iq-foundry-project-resource.services.ai.azure.com/api/projects/4iq-foundry-project"
)
EXPECTED_PROJECT_ID = (
    "/subscriptions/27b0139a-16b4-42bf-9ec9-c6db3768245e/"
    "resourceGroups/rg-aycabas-3iqs/providers/Microsoft.CognitiveServices/"
    "accounts/4iq-foundry-project-resource/projects/4iq-foundry-project"
)
EXPECTED_PROTOCOLS = [{"protocol": "responses", "version": "2.0.0"}]


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
    for name in EXPECTED_AGENT365_ENV:
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
    if "FOUNDRY_PROJECT_ENDPOINT" in environment_variables:
        problems.append(
            ConfigurationProblem(
                "agent.environmentVariables.FOUNDRY_PROJECT_ENDPOINT",
                "Foundry injects this value; it must not be configured in azure.yaml",
            )
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
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        "AZURE_SEARCH_ENDPOINT",
        "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
        "FABRIC_DATA_AGENT_MCP_URL",
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
        EXPECTED_PROJECT_ENDPOINT,
    )
    _expect(
        problems,
        "AZURE_AI_PROJECT_ID",
        env.get("AZURE_AI_PROJECT_ID"),
        EXPECTED_PROJECT_ID,
    )
    _expect(
        problems,
        "AZURE_AI_MODEL_DEPLOYMENT_NAME",
        env.get("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        EXPECTED_MODEL,
    )
    _expect(
        problems,
        "AZURE_SEARCH_ENDPOINT",
        env.get("AZURE_SEARCH_ENDPOINT"),
        EXPECTED_SEARCH_ENDPOINT,
    )
    _expect(
        problems,
        "FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
        env.get("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"),
        EXPECTED_KNOWLEDGE_BASE,
    )
    _expect(
        problems,
        "FABRIC_DATA_AGENT_MCP_URL",
        env.get("FABRIC_DATA_AGENT_MCP_URL"),
        EXPECTED_FABRIC_DATA_AGENT_MCP_URL,
    )
    _expect(
        problems,
        ".env.AZURE_SEARCH_ENDPOINT",
        local_env.get("AZURE_SEARCH_ENDPOINT"),
        EXPECTED_SEARCH_ENDPOINT,
    )
    _expect(
        problems,
        ".env.FOUNDRY_IQ_KNOWLEDGE_BASE_NAME",
        local_env.get("FOUNDRY_IQ_KNOWLEDGE_BASE_NAME"),
        EXPECTED_KNOWLEDGE_BASE,
    )
    _expect(
        problems,
        ".env.FABRIC_DATA_AGENT_MCP_URL",
        local_env.get("FABRIC_DATA_AGENT_MCP_URL"),
        EXPECTED_FABRIC_DATA_AGENT_MCP_URL,
    )
    for name, expected in EXPECTED_AGENT365_ENV.items():
        _expect(problems, name, env.get(name), expected)
        _expect(problems, f".env.{name}", local_env.get(name), expected)
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
    _expect(
        problems,
        "m365.manifest.id",
        m365_manifest.get("id"),
        EXPECTED_AGENT365_BLUEPRINT_ID,
    )
    _expect(
        problems,
        "m365.manifest.agenticUserTemplates[0].id",
        _nested_sequence(m365_manifest, "agenticUserTemplates", 0, "id"),
        EXPECTED_AGENT365_TEMPLATE_ID,
    )
    _expect(
        problems,
        "m365.manifest.agenticUserTemplates[0].file",
        _nested_sequence(m365_manifest, "agenticUserTemplates", 0, "file"),
        "agenticUserTemplateManifest.json",
    )
    _expect(
        problems,
        "m365.agenticUserTemplate.id",
        agentic_user_template.get("id"),
        EXPECTED_AGENT365_TEMPLATE_ID,
    )
    _expect(
        problems,
        "m365.agenticUserTemplate.agentIdentityBlueprintId",
        agentic_user_template.get("agentIdentityBlueprintId"),
        EXPECTED_AGENT365_BLUEPRINT_ID,
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
