"""ctypes mirror of ``omnibuscloud.h`` (ABI major 1).

Everything here is a literal transcription of the C header: status values,
core types, the versioned option structs and every ``oc_*`` prototype. The
struct sizes are asserted at import time against the same numbers the C/C++
hosts assert at compile time (``Client/tests/abi/oc_abi_asserts.h``), so a
layout drift between this file and the header fails loudly on the first
import instead of corrupting a call.
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, Structure, c_size_t, c_uint8, c_uint32, c_uint64

# --------------------------------------------------------------------------- #
# Versioning
# --------------------------------------------------------------------------- #

ABI_VERSION_MAJOR = 1
"""The ABI major this binding was written against; the library must match."""

ABI_VERSION_MINOR_REQUIRED = 6
"""The lowest ABI minor exposing every entry point this binding declares."""

# --------------------------------------------------------------------------- #
# Status codes (values frozen for ABI major 1)
# --------------------------------------------------------------------------- #

OC_OK = 0
OC_NO_EVENT = 1
OC_BUFFER_TOO_SMALL = 2
OC_INVALID_ARGUMENT = 3
OC_INVALID_HANDLE = 4
OC_INVALID_STATE = 5
OC_NOT_CONNECTED = 6
OC_UNAUTHORIZED = 7
OC_NOT_FOUND = 8
OC_CONFLICT = 9
OC_CANCELLED = 10
OC_TIMEOUT = 11
OC_NETWORK_ERROR = 12
OC_PROTOCOL_ERROR = 13
OC_IO_ERROR = 14
OC_INTERNAL_ERROR = 15

STATUS_NAMES = {
    OC_OK: "OC_OK",
    OC_NO_EVENT: "OC_NO_EVENT",
    OC_BUFFER_TOO_SMALL: "OC_BUFFER_TOO_SMALL",
    OC_INVALID_ARGUMENT: "OC_INVALID_ARGUMENT",
    OC_INVALID_HANDLE: "OC_INVALID_HANDLE",
    OC_INVALID_STATE: "OC_INVALID_STATE",
    OC_NOT_CONNECTED: "OC_NOT_CONNECTED",
    OC_UNAUTHORIZED: "OC_UNAUTHORIZED",
    OC_NOT_FOUND: "OC_NOT_FOUND",
    OC_CONFLICT: "OC_CONFLICT",
    OC_CANCELLED: "OC_CANCELLED",
    OC_TIMEOUT: "OC_TIMEOUT",
    OC_NETWORK_ERROR: "OC_NETWORK_ERROR",
    OC_PROTOCOL_ERROR: "OC_PROTOCOL_ERROR",
    OC_IO_ERROR: "OC_IO_ERROR",
    OC_INTERNAL_ERROR: "OC_INTERNAL_ERROR",
}

# --------------------------------------------------------------------------- #
# Core types
# --------------------------------------------------------------------------- #

oc_status = ctypes.c_int
oc_client_handle = c_uint64
oc_operation_id = c_uint64

OC_INVALID_CLIENT = 0


class oc_utf8_view(Structure):
    """A caller-owned UTF-8 byte span; ``data`` may be NULL only when ``length`` is 0."""

    _fields_ = [
        ("data", POINTER(c_uint8)),
        ("length", c_size_t),
    ]


class oc_client_options_v1(Structure):
    _fields_ = [
        ("struct_size", c_size_t),
        ("struct_version", c_uint32),
        ("endpoint", oc_utf8_view),
        ("identity_url", oc_utf8_view),
    ]


class oc_credentials_options_v1(Structure):
    _fields_ = [
        ("struct_size", c_size_t),
        ("struct_version", c_uint32),
        ("store_path", oc_utf8_view),
        ("max_age_days", c_uint32),
    ]


# The same layout fixtures the C and C++ hosts compile against.
assert ctypes.sizeof(oc_utf8_view) == 16, "oc_utf8_view layout"
assert ctypes.sizeof(oc_client_options_v1) == 48, "oc_client_options_v1 layout"
assert oc_client_options_v1.endpoint.offset == 16 and oc_client_options_v1.identity_url.offset == 32
assert ctypes.sizeof(oc_credentials_options_v1) == 40, "oc_credentials_options_v1 layout"
assert oc_credentials_options_v1.store_path.offset == 16 and oc_credentials_options_v1.max_age_days.offset == 32

# --------------------------------------------------------------------------- #
# Prototypes: name -> (restype, argtypes)
# --------------------------------------------------------------------------- #

_HANDLE_OP = (oc_status, [oc_client_handle, POINTER(oc_operation_id)])
_HANDLE_VIEW_OP = (oc_status, [oc_client_handle, oc_utf8_view, POINTER(oc_operation_id)])
_HANDLE_VIEW_VIEW_OP = (oc_status, [oc_client_handle, oc_utf8_view, oc_utf8_view, POINTER(oc_operation_id)])

PROTOTYPES = {
    "oc_get_abi_version": (c_uint32, []),
    "oc_get_sdk_version": (oc_status, [POINTER(c_uint8), c_size_t, POINTER(c_size_t)]),
    "oc_client_create": (oc_status, [POINTER(oc_client_options_v1), POINTER(oc_client_handle)]),
    "oc_client_release": (oc_status, [oc_client_handle]),
    "oc_client_connect_async": _HANDLE_OP,
    "oc_client_close_async": _HANDLE_OP,
    "oc_auth_login_browser_async": _HANDLE_OP,
    "oc_auth_logout_async": _HANDLE_OP,
    "oc_client_set_access_token": (oc_status, [oc_client_handle, oc_utf8_view]),
    "oc_credentials_attach": (oc_status, [oc_client_handle, POINTER(oc_credentials_options_v1)]),
    "oc_credentials_detach": (oc_status, [oc_client_handle, c_uint8]),
    "oc_credentials_restore_async": _HANDLE_OP,
    "oc_scopes_list_async": _HANDLE_OP,
    "oc_asset_upload_file_async": _HANDLE_VIEW_OP,
    "oc_asset_download_file_async": _HANDLE_VIEW_VIEW_OP,
    "oc_asset_query_async": _HANDLE_VIEW_OP,
    "oc_job_submit_async": _HANDLE_VIEW_OP,
    "oc_job_get_async": _HANDLE_VIEW_OP,
    "oc_job_cancel_async": _HANDLE_VIEW_OP,
    "oc_job_download_result_async": _HANDLE_VIEW_VIEW_OP,
    "oc_job_get_variable_async": _HANDLE_VIEW_VIEW_OP,
    "oc_operation_cancel": (oc_status, [oc_client_handle, oc_operation_id]),
    "oc_event_poll": (oc_status, [oc_client_handle, POINTER(c_uint8), c_size_t, POINTER(c_size_t)]),
}
"""Every entry point of ABI 1.6, in header order."""
