"""The job request document (schema v1) — the envelope every submission travels in.

The SDK core is controller-neutral: the request names a script, a scope, an
optional schedule and positional parameters of the published kinds. Complex
parameters are documents whose shapes a controller family publishes; the
generated ``<component>_documents.py`` bindings return them from
``to_parameter()``, and :class:`JobRequest` accepts anything with that method.
See ``Client/docs/job-request-schema.md``.
"""
from __future__ import annotations

import datetime as _datetime
import json
import uuid as _uuid
from typing import Any, Protocol, runtime_checkable

SCHEMA_VERSION = 1


@runtime_checkable
class ParameterLike(Protocol):
    """Anything that renders itself as a request parameter (the generated document bindings do)."""

    def to_parameter(self) -> dict[str, Any]: ...


# --------------------------------------------------------------------------- #
# Parameter kinds
# --------------------------------------------------------------------------- #

def int32(value: int) -> dict[str, Any]:
    return {"kind": "int32", "value": int(value)}


def int64(value: int) -> dict[str, Any]:
    return {"kind": "int64", "value": int(value)}


def double(value: float) -> dict[str, Any]:
    return {"kind": "double", "value": float(value)}


def boolean(value: bool) -> dict[str, Any]:
    return {"kind": "bool", "value": bool(value)}


def string(value: str) -> dict[str, Any]:
    return {"kind": "string", "value": str(value)}


def uuid(value: "_uuid.UUID | str") -> dict[str, Any]:
    return {"kind": "uuid", "value": str(_uuid.UUID(str(value)))}


def date_time(value: "_datetime.datetime | str") -> dict[str, Any]:
    return {"kind": "dateTime", "value": value if isinstance(value, str) else _iso(value)}


def null() -> dict[str, Any]:
    return {"kind": "null"}


def document(type_id: str, value: dict[str, Any]) -> dict[str, Any]:
    """A raw document parameter for hosts that compose the value themselves."""
    return {"kind": "document", "type": type_id, "value": dict(value)}


def parameter(value: Any) -> dict[str, Any]:
    """Coerces a Python value into a parameter: documents via ``to_parameter()``,
    ready-made parameter dicts as-is, ``bool``/``int``/``float``/``str``/``UUID``/
    ``datetime``/``None`` to their kinds. Ints outside int32 become int64."""
    if isinstance(value, ParameterLike):
        return value.to_parameter()
    if isinstance(value, dict) and "kind" in value:
        return value
    if value is None:
        return null()
    if isinstance(value, bool):
        return boolean(value)
    if isinstance(value, int):
        return int32(value) if -2**31 <= value < 2**31 else int64(value)
    if isinstance(value, float):
        return double(value)
    if isinstance(value, str):
        return string(value)
    if isinstance(value, _uuid.UUID):
        return uuid(value)
    if isinstance(value, _datetime.datetime):
        return date_time(value)
    raise TypeError(f"cannot express {type(value).__name__} as a job request parameter; pass a document binding or an explicit kind")


# --------------------------------------------------------------------------- #
# The envelope
# --------------------------------------------------------------------------- #

class JobRequest:
    """Builder for the job request document.

    ``JobRequest("RenderStill").project(pid).params(scene, 12, options).to_json()``
    """

    def __init__(self, script: str):
        if not script or not script.strip():
            raise ValueError("script name is required")
        self._script = script
        self._client_group_id: str | None = None
        self._project_id: str | None = None
        self._scheduled_for_utc: str | None = None
        self._parameters: list[dict[str, Any]] = []

    def client_group(self, client_group_id: "_uuid.UUID | str | None") -> "JobRequest":
        """Targets a client group (mutually exclusive with :meth:`project`)."""
        self._client_group_id = None if client_group_id is None else str(_uuid.UUID(str(client_group_id)))
        return self

    def project(self, project_id: "_uuid.UUID | str | None") -> "JobRequest":
        """Targets a project (mutually exclusive with :meth:`client_group`)."""
        self._project_id = None if project_id is None else str(_uuid.UUID(str(project_id)))
        return self

    def scheduled_for(self, when: "_datetime.datetime | str | None") -> "JobRequest":
        self._scheduled_for_utc = None if when is None else (when if isinstance(when, str) else _iso(when))
        return self

    def param(self, value: Any) -> "JobRequest":
        """Appends one positional parameter (see :func:`parameter` for coercions)."""
        self._parameters.append(parameter(value))
        return self

    def params(self, *values: Any) -> "JobRequest":
        for value in values:
            self.param(value)
        return self

    def to_dict(self) -> dict[str, Any]:
        if self._client_group_id and self._project_id:
            raise ValueError("a request targets either a client group or a project, not both")

        request: dict[str, Any] = {"schemaVersion": SCHEMA_VERSION, "script": self._script}

        scope: dict[str, Any] = {}
        if self._client_group_id:
            scope["clientGroupId"] = self._client_group_id
        if self._project_id:
            scope["projectId"] = self._project_id
        if scope:
            request["scope"] = scope

        if self._scheduled_for_utc:
            request["scheduledForUtc"] = self._scheduled_for_utc

        if self._parameters:
            request["parameters"] = list(self._parameters)

        return request

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    @property
    def script(self) -> str:
        return self._script


def _iso(value: _datetime.datetime) -> str:
    text = value.strftime("%Y-%m-%dT%H:%M:%S")
    if value.microsecond:
        text += "." + f"{value.microsecond:06d}".rstrip("0")
    offset = value.utcoffset()
    if offset is None:
        return text + "Z"
    if offset == _datetime.timedelta(0):
        return text + "Z"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return text + f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"
