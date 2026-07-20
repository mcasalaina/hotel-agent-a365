from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProxySettings:
    entra_tenant_id: str
    entra_audience: str
    entra_required_scope: str
    foundry_project_endpoint: str
    foundry_agent_name: str
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8080
    session_ttl_seconds: int = 600
    max_sessions: int = 2_000

    @classmethod
    def from_environment(cls) -> ProxySettings:
        environment = os.getenv("VOICE_PROXY_ENVIRONMENT", "development")
        if environment not in {"development", "staging", "production"}:
            raise RuntimeError(
                "VOICE_PROXY_ENVIRONMENT must be development, staging, or production"
            )
        return cls(
            entra_tenant_id=_required("ENTRA_TENANT_ID"),
            entra_audience=_required("ENTRA_API_AUDIENCE"),
            entra_required_scope=_required("ENTRA_REQUIRED_SCOPE"),
            foundry_project_endpoint=_required("FOUNDRY_PROJECT_ENDPOINT"),
            foundry_agent_name=os.getenv("FOUNDRY_AGENT_NAME", "hotel-servicing-agent"),
            environment=environment,
            host=os.getenv("VOICE_PROXY_HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8080")),
            session_ttl_seconds=int(os.getenv("VOICE_SESSION_TTL_SECONDS", "600")),
            max_sessions=int(os.getenv("VOICE_MAX_SESSIONS", "2000")),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value
