"""Loading the native library — once per process, by contract.

The NativeAOT library is process-lifetime and non-unloadable (02-native-sdk.md
section 4): :func:`load` is idempotent, a second call with the same path
returns the same :class:`Library`, and a call with a DIFFERENT path is
refused — a library file replaced on disk takes effect only after the host
process restarts. Blender addon disable/enable therefore reuses the loaded
instance.
"""
from __future__ import annotations

import ctypes
import os
import platform
import sys
import threading
from ctypes import POINTER, byref, c_size_t, c_uint8

from . import _abi
from .errors import LibraryError, raise_for

_lock = threading.Lock()
_loaded: "Library | None" = None


class Library:
    """The loaded native library: resolved entry points plus the version facts."""

    def __init__(self, path: str):
        try:
            self._cdll = ctypes.CDLL(path)
        except OSError as ex:
            raise LibraryError(f"failed to load native library {path!r}: {ex}") from ex

        self._path = path
        self._fns: dict[str, object] = {}

        for name, (restype, argtypes) in _abi.PROTOTYPES.items():
            try:
                fn = getattr(self._cdll, name)
            except AttributeError as ex:
                raise LibraryError(f"native library {path!r} lacks entry point {name} (older ABI?)") from ex
            fn.restype = restype
            fn.argtypes = argtypes
            self._fns[name] = fn

        self._abi_version = int(self.fn("oc_get_abi_version")())
        if self.abi_major != _abi.ABI_VERSION_MAJOR:
            raise LibraryError(
                f"native library {path!r} has ABI major {self.abi_major}; this binding needs {_abi.ABI_VERSION_MAJOR}")
        if self.abi_minor < _abi.ABI_VERSION_MINOR_REQUIRED:
            raise LibraryError(
                f"native library {path!r} has ABI 1.{self.abi_minor}; this binding needs 1.{_abi.ABI_VERSION_MINOR_REQUIRED}+")

        self._sdk_version = self._read_sdk_version()

    # ------------------------------------------------------------------ #

    def fn(self, name: str):
        """A resolved entry point (ctypes function) by symbol name."""
        return self._fns[name]

    def _read_sdk_version(self) -> str:
        get = self.fn("oc_get_sdk_version")
        required = c_size_t(0)
        status = get(None, 0, byref(required))
        if status not in (_abi.OC_BUFFER_TOO_SMALL, _abi.OC_OK):
            raise_for(status, "oc_get_sdk_version")
        buffer = (c_uint8 * max(1, required.value))()
        written = c_size_t(0)
        raise_for(get(buffer, len(buffer), byref(written)), "oc_get_sdk_version")
        return bytes(buffer[: max(0, written.value - 1)]).decode("utf-8")

    @property
    def path(self) -> str:
        return self._path

    @property
    def abi_version(self) -> int:
        """Packed ``(major << 16) | minor``."""
        return self._abi_version

    @property
    def abi_major(self) -> int:
        return self._abi_version >> 16

    @property
    def abi_minor(self) -> int:
        return self._abi_version & 0xFFFF

    @property
    def sdk_version(self) -> str:
        return self._sdk_version


def library_file_name() -> str:
    """The platform's library file name (``omnibuscloud_native.dll`` / ``libomnibuscloud_native.so`` / ``.dylib``)."""
    if sys.platform.startswith("win"):
        return "omnibuscloud_native.dll"
    if sys.platform == "darwin":
        return "libomnibuscloud_native.dylib"
    return "libomnibuscloud_native.so"


def runtime_identifier() -> str:
    """The .NET RID of this process: win-x64, linux-x64, osx-arm64 (others unsupported by the SDK)."""
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
    if sys.platform.startswith("win"):
        return f"win-{arch}"
    if sys.platform == "darwin":
        return f"osx-{arch}"
    return f"linux-{arch}"


def default_library_path() -> str | None:
    """Where a vendored library is looked for when :func:`load` gets no path:
    ``$OMNIBUSCLOUD_NATIVE`` (a file), then ``<pyoc>/native/<rid>/<file>``, then ``<pyoc>/native/<file>``."""
    candidate = os.environ.get("OMNIBUSCLOUD_NATIVE")
    if candidate and os.path.isfile(candidate):
        return candidate

    here = os.path.dirname(os.path.abspath(__file__))
    for relative in (os.path.join("native", runtime_identifier(), library_file_name()), os.path.join("native", library_file_name())):
        candidate = os.path.join(here, relative)
        if os.path.isfile(candidate):
            return candidate

    return None


def load(path: str | None = None) -> Library:
    """Loads the native library once per process and returns it.

    :param path: the library file; ``None`` uses :func:`default_library_path`.
    :raises LibraryError: when nothing is found, the file cannot be loaded, the
        ABI does not match, or a different path is passed after a load.
    """
    global _loaded

    resolved = path or default_library_path()
    if resolved is None:
        raise LibraryError(
            "no native library: pass load(path) or set OMNIBUSCLOUD_NATIVE / vendor it under pyoc/native/<rid>/")
    resolved = os.path.abspath(resolved)

    with _lock:
        if _loaded is not None:
            if os.path.normcase(_loaded.path) != os.path.normcase(resolved):
                raise LibraryError(
                    f"the native library is already loaded from {_loaded.path!r}; it is process-lifetime — "
                    f"a different file ({resolved!r}) takes effect only after the host restarts")
            return _loaded

        _loaded = Library(resolved)
        return _loaded


def loaded() -> Library | None:
    """The library loaded in this process, or ``None``."""
    return _loaded


def require() -> Library:
    """The loaded library; raises :class:`LibraryError` when :func:`load` was never called."""
    if _loaded is None:
        raise LibraryError("the native library is not loaded; call pyoc.load(path) first")
    return _loaded


def make_view(data: bytes | None):
    """An ``oc_utf8_view`` over ``data`` plus the buffer that must outlive the call."""
    if not data:
        view = _abi.oc_utf8_view()
        view.data = None
        view.length = 0
        return view, None

    buffer = ctypes.create_string_buffer(data, len(data))
    view = _abi.oc_utf8_view()
    view.data = ctypes.cast(buffer, POINTER(c_uint8))
    view.length = len(data)
    return view, buffer
