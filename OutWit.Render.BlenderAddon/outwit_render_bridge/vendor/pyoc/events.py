"""The v1 event envelope as a typed Python object."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

CONNECTION_STATE = "connection-state"
AUTHORIZATION_REQUIRED = "authorization-required"
OPERATION_PROGRESS = "operation-progress"
OPERATION_COMPLETED = "operation-completed"
OPERATION_FAILED = "operation-failed"

TERMINAL_TYPES = frozenset({OPERATION_COMPLETED, OPERATION_FAILED})


@dataclass(frozen=True)
class Event:
    """One envelope from ``oc_event_poll``; ``payload`` keeps the type-specific fields."""

    schema_version: int
    sequence: int
    type: str
    client: int
    operation: int | None
    timestamp_utc: str
    payload: dict[str, Any] = field(default_factory=dict)
    raw: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.type in TERMINAL_TYPES

    @property
    def is_completed(self) -> bool:
        return self.type == OPERATION_COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.type == OPERATION_FAILED

    @property
    def status(self) -> int | None:
        """``operation-failed``: the numeric ``oc_status`` category."""
        value = self.payload.get("status")
        return int(value) if value is not None else None

    @property
    def message(self) -> str:
        """``operation-failed``: the bounded diagnostic."""
        return str(self.payload.get("message") or "")

    @property
    def state(self) -> str | None:
        """``connection-state``: created | connecting | connected | closing | closed."""
        return self.payload.get("state")

    @staticmethod
    def parse(raw: str) -> "Event":
        """Parses one envelope; a malformed envelope raises ``ValueError`` with the raw text kept."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as ex:
            raise ValueError(f"malformed event envelope: {ex}: {raw[:200]}") from ex

        if not isinstance(data, dict):
            raise ValueError(f"malformed event envelope: not an object: {raw[:200]}")

        operation = data.get("operation")

        return Event(
            schema_version=int(data.get("schemaVersion", 0)),
            sequence=int(data.get("sequence", 0)),
            type=str(data.get("type", "")),
            client=int(data.get("client", 0)),
            operation=int(operation) if operation is not None else None,
            timestamp_utc=str(data.get("timestampUtc", "")),
            payload=dict(data.get("payload") or {}),
            raw=raw,
        )
