from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from hotel_assert.constants import (
    DEFAULT_AGENT_NAME,
    DEFAULT_API_VERSION,
    DEFAULT_SIDECAR_SERVICE,
    DEFAULT_SIDECAR_URL,
    MAX_HISTORY_MESSAGES,
)
from hotel_assert.correlation import (
    CorrelationLedger,
    CorrelationRecord,
    ScenarioCorrelation,
    completed_at,
)
from hotel_assert.foundry import FoundryTargetConfig, invoke_hosted_agent
from hotel_assert.identity import (
    AgentUserTokenValidator,
    IdentityRequirements,
    SidecarTokenClient,
)


class TargetConfigurationError(RuntimeError):
    """Raised when the live ASSERT target is not fully configured."""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise TargetConfigurationError(f"Missing required environment variable: {name}")
    return value


class Agent365Target:
    def __init__(self) -> None:
        requirements = IdentityRequirements(
            tenant_id=_required("ASSERT_TENANT_ID"),
            audience=_required("ASSERT_FOUNDRY_AUDIENCE"),
            agent_user_id=_required("ASSERT_AGENT_USER_ID"),
            agent_identity_id=_required("ASSERT_AGENT_IDENTITY_ID"),
            parent_blueprint_id=_required("ASSERT_PARENT_BLUEPRINT_ID"),
        )
        self.sidecar = SidecarTokenClient(
            base_url=os.getenv("ASSERT_SIDECAR_URL", DEFAULT_SIDECAR_URL),
            service_name=os.getenv("ASSERT_SIDECAR_SERVICE", DEFAULT_SIDECAR_SERVICE),
            agent_identity_id=requirements.agent_identity_id,
            agent_user_id=requirements.agent_user_id,
            validator=AgentUserTokenValidator(requirements),
        )
        self.foundry = FoundryTargetConfig(
            endpoint=_required("AZURE_AI_FOUNDRY_ENDPOINT"),
            agent_name=os.getenv("FOUNDRY_AGENT_NAME", DEFAULT_AGENT_NAME),
            model=_required("FOUNDRY_MODEL_NAME"),
            api_version=os.getenv("FOUNDRY_API_VERSION", DEFAULT_API_VERSION),
        )
        run_id = os.getenv("ASSERT_RUN_ID", f"local-{uuid4()}")
        ledger_path = Path(
            os.getenv(
                "ASSERT_CORRELATION_LEDGER",
                f"artifacts/results/correlation/{run_id}.jsonl",
            )
        )
        self.correlation = ScenarioCorrelation(run_id, CorrelationLedger(ledger_path))

    async def chat(self, message: str, history: list[dict[str, str]]) -> str:
        if not history:
            raise ValueError("ASSERT history must include the current user message")
        last_user = next(
            (item.get("content") for item in reversed(history) if item.get("role") == "user"),
            None,
        )
        if last_user != message:
            raise ValueError("ASSERT message must match the final user turn in history")

        context = self.correlation.begin_turn(history)
        identity = await self.sidecar.acquire()
        bounded_history = history[-MAX_HISTORY_MESSAGES:]
        baggage = (
            f"assert.run_id={quote(str(context['run_id']))},"
            f"assert.case_id={quote(str(context['case_id']))},"
            f"session.id={quote(str(context['session_id']))}"
        )
        text, response_id = await invoke_hosted_agent(
            config=self.foundry,
            token=identity.token,
            history=bounded_history,
            traceparent=str(context["traceparent"]),
            baggage=baggage,
        )
        self.correlation.ledger.append(
            CorrelationRecord(
                run_id=str(context["run_id"]),
                case_id=str(context["case_id"]),
                session_id=str(context["session_id"]),
                turn_index=int(context["turn_index"]),
                trace_id=str(context["trace_id"]),
                parent_span_id=str(context["parent_span_id"]),
                response_id=response_id,
                started_at=str(context["started_at"]),
                completed_at=completed_at(),
                identity=identity.audit_record(),
            )
        )
        return text


_target: Agent365Target | None = None


async def chat(message: str, history: list[dict[str, str]]) -> str:
    global _target
    if _target is None:
        _target = Agent365Target()
    return await _target.chat(message, history)
