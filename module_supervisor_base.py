"""Base class for all module supervisors in DTF_EMPIRE."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class ModuleSupervisor(ABC):
    def __init__(self, name: str) -> None:
        self.name = name
        self.state: Dict[str, Any] = {}
        self._initialized: bool = False

    @abstractmethod
    def initialize(self) -> None:
        ...

    @abstractmethod
    def handle_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        ...

    @abstractmethod
    def get_health_snapshot(self) -> Dict[str, Any]:
        ...

    def mark_initialized(self) -> None:
        self._initialized = True

    @property
    def initialized(self) -> bool:
        return self._initialized

    def record_metric(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get_metric(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

