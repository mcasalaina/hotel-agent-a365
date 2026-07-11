from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrchestrationRequest:
    session_id: str
    user_input: str

    def status_message(self) -> str:
        return "Preparing the guest-services request."
