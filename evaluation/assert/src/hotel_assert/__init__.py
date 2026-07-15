"""ASSERT integration for the Hotel Guest Services agent."""

__all__ = ["chat"]


async def chat(message: str, history: list[dict[str, str]]) -> str:
    """Load the live target lazily so offline tools do not require target configuration."""
    from hotel_assert.target import chat as target_chat

    return await target_chat(message, history)
