from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    project_endpoint: str
    model_deployment: str
    instructions: str

    @classmethod
    def from_environment(cls) -> Settings:
        dotenv_path = os.getenv("DOTENV_PATH")
        load_dotenv(dotenv_path=dotenv_path or None)
        project_endpoint = _required_environment_variable("FOUNDRY_PROJECT_ENDPOINT")
        model_deployment = _required_environment_variable("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        instructions_path = Path(
            os.getenv("AGENT_INSTRUCTIONS_PATH", "../../agent-instructions.md")
        )
        if not instructions_path.is_file():
            raise FileNotFoundError(f"Agent instructions file does not exist: {instructions_path}")
        return cls(
            project_endpoint=project_endpoint,
            model_deployment=model_deployment,
            instructions=instructions_path.read_text(encoding="utf-8"),
        )


def _required_environment_variable(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value
