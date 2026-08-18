"""pyoc — the Python (ctypes) face of the OmnibusCloud native SDK.

Blender-free by requirement (05-blender-sdk-migration.md, section 6): a plain
binding over ``omnibuscloud_native`` for any Python host, and the SDK's own
Python acceptance artifact. Standard library only.

    import pyoc
    pyoc.load("/path/to/omnibuscloud_native.dll")          # once per process
    with pyoc.Client("https://engine.omnibuscloud.com", "https://id.omnibuscloud.com") as client:
        client.set_access_token(token)                       # or client.login_browser() + wait
        client.wait(client.connect())
        scopes = client.wait(client.scopes_list())["scopes"]
        request = pyoc.JobRequest("RenderStill").params(scene_ref, 12, options)
        job = client.wait(client.job_submit(request))["job"]
        client.wait(client.close())
"""
from __future__ import annotations

from . import documents, errors, events
from ._abi import (
    ABI_VERSION_MAJOR,
    ABI_VERSION_MINOR_REQUIRED,
    OC_BUFFER_TOO_SMALL,
    OC_CANCELLED,
    OC_CONFLICT,
    OC_INTERNAL_ERROR,
    OC_INVALID_ARGUMENT,
    OC_INVALID_HANDLE,
    OC_INVALID_STATE,
    OC_IO_ERROR,
    OC_NETWORK_ERROR,
    OC_NO_EVENT,
    OC_NOT_CONNECTED,
    OC_NOT_FOUND,
    OC_OK,
    OC_PROTOCOL_ERROR,
    OC_TIMEOUT,
    OC_UNAUTHORIZED,
    STATUS_NAMES,
)
from .client import Client
from .documents import JobRequest
from .errors import (
    BufferTooSmall,
    Cancelled,
    Conflict,
    InternalError,
    InvalidArgument,
    InvalidHandle,
    InvalidState,
    IoError,
    LibraryError,
    NetworkError,
    NotConnected,
    NotFound,
    OcError,
    OperationFailed,
    ProtocolError,
    Timeout,
    Unauthorized,
)
from .events import Event
from .library import Library, default_library_path, library_file_name, load, loaded, require, runtime_identifier

__version__ = "0.1.0"

__all__ = [
    "ABI_VERSION_MAJOR",
    "ABI_VERSION_MINOR_REQUIRED",
    "BufferTooSmall",
    "Cancelled",
    "Client",
    "Conflict",
    "Event",
    "InternalError",
    "InvalidArgument",
    "InvalidHandle",
    "InvalidState",
    "IoError",
    "JobRequest",
    "Library",
    "LibraryError",
    "NetworkError",
    "NotConnected",
    "NotFound",
    "OC_BUFFER_TOO_SMALL",
    "OC_CANCELLED",
    "OC_CONFLICT",
    "OC_INTERNAL_ERROR",
    "OC_INVALID_ARGUMENT",
    "OC_INVALID_HANDLE",
    "OC_INVALID_STATE",
    "OC_IO_ERROR",
    "OC_NETWORK_ERROR",
    "OC_NO_EVENT",
    "OC_NOT_CONNECTED",
    "OC_NOT_FOUND",
    "OC_OK",
    "OC_PROTOCOL_ERROR",
    "OC_TIMEOUT",
    "OC_UNAUTHORIZED",
    "OcError",
    "OperationFailed",
    "ProtocolError",
    "STATUS_NAMES",
    "Timeout",
    "Unauthorized",
    "default_library_path",
    "documents",
    "errors",
    "events",
    "library_file_name",
    "load",
    "loaded",
    "require",
    "runtime_identifier",
]
