from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    permission: str = "standard"


class Connector(ABC):
    """Application-neutral contract implemented by every integration."""

    id: str
    name: str
    category: str
    description: str

    @abstractmethod
    def probe(self, local_agent_connected: bool) -> dict[str, Any]: ...

    @abstractmethod
    def tools(self) -> list[ToolSpec]: ...

    @abstractmethod
    def execute(self, tool: str, parameters: dict[str, Any]) -> ToolResult: ...

    def manifest(self, local_agent_connected: bool) -> dict[str, Any]:
        state = self.probe(local_agent_connected)
        return {
            "id": self.id, "name": self.name, "category": self.category,
            "description": self.description, **state,
            "tools": [asdict(tool) for tool in self.tools()],
            "capabilities": [tool.name.replace("_", " ").title() for tool in self.tools()],
        }

