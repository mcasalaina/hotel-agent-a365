from abc import ABC, abstractmethod
from typing import Optional

from microsoft_agents.hosting.core import Authorization, TurnContext


class AgentInterface(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize external connections."""

    @abstractmethod
    async def process_user_message(
        self,
        message: str,
        auth: Authorization,
        auth_handler_name: Optional[str],
        context: TurnContext,
    ) -> str:
        """Process one user message."""

    @abstractmethod
    async def cleanup(self) -> None:
        """Release external resources."""


def validate_agent_class(agent_class: type[AgentInterface]) -> None:
    if not issubclass(agent_class, AgentInterface):
        raise TypeError(f"{agent_class.__name__} must inherit from AgentInterface")
