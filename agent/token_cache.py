from typing import Optional

_agentic_tokens: dict[str, str] = {}


def cache_agentic_token(tenant_id: str, agent_id: str, token: str) -> None:
    _agentic_tokens[f"{tenant_id}:{agent_id}"] = token


def get_cached_agentic_token(tenant_id: str, agent_id: str) -> Optional[str]:
    return _agentic_tokens.get(f"{tenant_id}:{agent_id}")
