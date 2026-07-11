from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SessionState:
    session_id: str
    status_events: list[str] = field(default_factory=list)

    def record_status(self, message: str) -> None:
        self.status_events.append(message)
