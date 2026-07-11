from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

ToolHandler = Callable[..., object]


@dataclass(slots=True)
class ToolRegistry:
    _handlers: dict[str, ToolHandler] = field(default_factory=dict)

    def register(self, name: str, handler: ToolHandler) -> None:
        if name in self._handlers:
            raise ValueError(f"Tool is already registered: {name}")
        self._handlers[name] = handler

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
