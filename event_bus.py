"""Core in-process event bus implementation for DTF_EMPIRE."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any, Callable, DefaultDict, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class EventHandler(Protocol):
    def __call__(self, payload: Dict[str, Any]) -> None:
        ...


class EventBus:
    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, List[EventHandler]] = defaultdict(list)
        self._wildcard_subscribers: DefaultDict[str, List[EventHandler]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type.endswith(".*"):
            namespace = event_type[:-2]
            self._wildcard_subscribers[namespace].append(handler)
        else:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type.endswith(".*"):
            namespace = event_type[:-2]
            handlers = self._wildcard_subscribers.get(namespace, [])
            if handler in handlers:
                handlers.remove(handler)
        else:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event_type: str, payload: Dict[str, Any] | None = None) -> None:
        if payload is None:
            payload = {}

        with self._lock:
            exact_handlers = list(self._subscribers.get(event_type, []))
            namespace = event_type.split(".", 1)[0] if "." in event_type else event_type
            wildcard_handlers = list(self._wildcard_subscribers.get(namespace, []))

        for handler in exact_handlers + wildcard_handlers:
            try:
                handler(payload)
            except Exception as exc:
                print(f"[EVENT_BUS] Handler error for {event_type}: {exc!r}")


event_bus = EventBus()

