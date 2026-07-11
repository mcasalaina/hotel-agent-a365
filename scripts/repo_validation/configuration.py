from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

EXPECTED_AGENT_NAME = "hotel-servicing-agent"
EXPECTED_MODEL = "gpt-5.4-mini"
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
    evaluation = _load_yaml(root / "eval.yaml")
    env = _load_env(root / "config/azd.env.example")
    problems: list[ConfigurationProblem] = []

    services = _mapping(azure.get("services"))
    infrastructure = _mapping(azure.get("infra"))
    project = _mapping(services.get("ai-project"))
    agent = _mapping(services.get(EXPECTED_AGENT_NAME))
    template = _mapping(manifest.get("template"))

    _expect(problems, "azure.name", azure.get("name"), "hotel-agent-a365")
    _expect(problems, "infra.provider", infrastructure.get("provider"), "bicep")
    _expect(problems, "infra.path", infrastructure.get("path"), "infra")
    _expect(problems, "services.ai-project.host", project.get("host"), "azure.ai.project")
    _expect(
        problems,
        "services.ai-project.endpoint",
        project.get("endpoint"),
        "${AZURE_AI_PROJECT_ENDPOINT}",
    )
    _expect(problems, "agent.host", agent.get("host"), "azure.ai.agent")
    _expect(problems, "agent.kind", agent.get("kind"), "hosted")
    _expect(problems, "agent.name", agent.get("name"), EXPECTED_AGENT_NAME)
    _expect(problems, "agent.language", agent.get("language"), "docker")
    _expect(problems, "agent.protocols", agent.get("protocols"), EXPECTED_PROTOCOLS)
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
        "agent.env.AZURE_AI_MODEL_DEPLOYMENT_NAME",
        _nested(agent, "env", "AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        "${AZURE_AI_MODEL_DEPLOYMENT_NAME}",
    )

    _expect(problems, "manifest.template.name", template.get("name"), EXPECTED_AGENT_NAME)
    _expect(problems, "manifest.template.kind", template.get("kind"), "hosted")
    _expect(
        problems,
        "manifest.template.protocols",
        template.get("protocols"),
        EXPECTED_PROTOCOLS,
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
    for infrastructure_file in (
        "infra/main.bicep",
        "infra/main.parameters.json",
        "infra/modules/supporting-resources.bicep",
        "infra/modules/foundry-connection.bicep",
    ):
        if not (root / infrastructure_file).is_file():
            problems.append(
                ConfigurationProblem(
                    infrastructure_file,
                    "required infrastructure file does not exist",
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
