"""
Alternate data streams / xattrs / MotW (F8) — ADS + Zone.Identifier.

- Windows: ``FindFirstStreamW``/``FindNextStreamW`` via ``ctypes`` (or
  ``ntfsutils`` if installed) for NTFS ADS + ``Zone.Identifier`` (MotW).
- Linux/macOS: ``os.listxattr`` / ``os.getxattr`` fallback + ``xattr`` lib.

Exposes :data:`HAS_XATTR` so callers degrade gracefully.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field


HAS_XATTR: bool = hasattr(os, "listxattr") or importlib.util.find_spec("xattr") is not None
HAS_NTFSUTILS: bool = importlib.util.find_spec("ntfsutils") is not None
# Re-export other HAS flags for uniform caller checks
HAS_LIBEWF: bool = importlib.util.find_spec("pyewf") is not None
HAS_YARA: bool = importlib.util.find_spec("yara") is not None
HAS_SSDEEP: bool = importlib.util.find_spec("ssdeep") is not None


@dataclass
class AlternateStream:
    """One alternate stream / xattr.

    Attributes:
        name: Stream or xattr name.  Windows ADS names include the leading
              ``:`` (e.g. ``:Zone.Identifier``); Linux xattr names include
              the namespace (e.g. ``user.test``).
        size: Size of the stream/xattr value in bytes.
        xattrs: Mapping of xattr name → raw bytes value.  For Windows ADS
                this is empty unless the stream was also surfaced as xattr.
    """

    name: str
    size: int
    xattrs: dict = field(default_factory=dict)


def _list_streams_windows(path: str) -> list[AlternateStream]:
    """Enumerate NTFS ADS on Windows via ctypes or ntfsutils."""
    results: list[AlternateStream] = []

    # Try ntfsutils first if available
    if HAS_NTFSUTILS:
        try:
            # ntfsutils is not a stable API; attempt best-effort
            import ntfsutils  # type: ignore

            # Some forks expose list_streams; try generically
            if hasattr(ntfsutils, "list_streams"):
                try:
                    streams = ntfsutils.list_streams(path)  # type: ignore[attr-defined]
                    for s in streams:  # type: ignore
                        name = getattr(s, "name", str(s))
                        size = int(getattr(s, "size", 0))
                        results.append(AlternateStream(name=name, size=size, xattrs={}))
                    if results:
                        return results
                except Exception:
                    pass
        except Exception:
            pass

    # ctypes FindFirstStreamW / FindNextStreamW
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        class WIN32_FIND_STREAM_DATA(ctypes.Structure):
            _fields_ = [
                ("StreamSize", ctypes.c_int64),
                ("cStreamName", wintypes.WCHAR * 296),
            ]

        FindFirstStreamW = kernel32.FindFirstStreamW
        FindFirstStreamW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(WIN32_FIND_STREAM_DATA), wintypes.DWORD]
        FindFirstStreamW.restype = wintypes.HANDLE

        FindNextStreamW = kernel32.FindNextStreamW
        FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.POINTER(WIN32_FIND_STREAM_DATA)]
        FindNextStreamW.restype = wintypes.BOOL

        FindClose = kernel32.FindClose
        FindClose.argtypes = [wintypes.HANDLE]

        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

        data = WIN32_FIND_STREAM_DATA()
        handle = FindFirstStreamW(path, 0, ctypes.byref(data), 0)
        if handle == INVALID_HANDLE_VALUE or handle is None or handle == wintypes.HANDLE(-1).value:  # type: ignore
            # No streams or API not available — fall through to MotW check
            pass
        else:
            try:
                while True:
                    name = data.cStreamName
                    # cStreamName is like "::$DATA" for default, ":Zone.Identifier:$DATA" for ADS
                    # Strip trailing :$DATA
                    if name.endswith(":$DATA"):
                        name = name[: -len(":$DATA")]
                    if name == "":
                        name = "::$DATA"
                    # Skip default data stream (::$DATA)
                    if name != "::$DATA" and name != "":
                        size = int(data.StreamSize)
                        # Try to read stream content for size verification
                        # Don't fail if unreadable
                        results.append(AlternateStream(name=name, size=size, xattrs={}))
                    if not FindNextStreamW(handle, ctypes.byref(data)):
                        break
            finally:
                try:
                    FindClose(handle)
                except Exception:
                    pass
    except Exception:
        # ctypes not available or path not on NTFS — ignore
        pass

    # MotW is an ADS named :Zone.Identifier — also try direct file existence
    # On Windows, ADS is accessed as "path:Zone.Identifier"
    motw_name = ":Zone.Identifier"
    motw_path = f"{path}{motw_name}"
    try:
        if os.path.exists(motw_path):
            try:
                sz = os.path.getsize(motw_path)
            except OSError:
                sz = 0
            # Avoid duplicate if already found via FindFirstStreamW
            if not any(r.name == motw_name for r in results):
                # Try to read content for MotW parsing but not required
                results.append(AlternateStream(name=motw_name, size=sz, xattrs={}))
        else:
            # Some Python builds don't support ADS path; try reading via open
            try:
                with open(motw_path, "rb") as fh:
                    data = fh.read()
                if not any(r.name == motw_name for r in results):
                    results.append(AlternateStream(name=motw_name, size=len(data), xattrs={}))
            except (OSError, IOError):
                pass
    except Exception:
        pass

    return results


def _list_streams_posix(path: str) -> list[AlternateStream]:
    """Enumerate xattrs on Linux/macOS via os.listxattr / xattr."""
    results: list[AlternateStream] = []

    # Primary: os.listxattr (Linux/macOS)
    if hasattr(os, "listxattr"):
        try:
            attrs = os.listxattr(path)  # type: ignore[attr-defined]
            for attr in attrs:
                # attrs may be bytes on some platforms
                if isinstance(attr, bytes):
                    attr_name = attr.decode("utf-8", errors="surrogateescape")
                    attr_key = attr
                else:
                    attr_name = str(attr)
                    attr_key = attr_name
                try:
                    if isinstance(attr_key, bytes):
                        val = os.getxattr(path, attr_key)  # type: ignore[attr-defined]
                    else:
                        val = os.getxattr(path, attr_name)  # type: ignore[attr-defined]
                except OSError:
                    val = b""
                if isinstance(val, str):
                    val_bytes = val.encode("utf-8")
                elif isinstance(val, (bytes, bytearray)):
                    val_bytes = bytes(val)
                else:
                    val_bytes = str(val).encode("utf-8")
                size = len(val_bytes)
                # xattrs dict stores raw bytes as in spec: {name: b'42'}
                results.append(AlternateStream(name=attr_name, size=size, xattrs={attr_name: val_bytes}))
            if results:
                return results
        except OSError:
            pass
        except Exception:
            pass

    # Fallback: xattr third-party lib
    if importlib.util.find_spec("xattr") is not None:
        try:
            import xattr  # type: ignore

            try:
                # xattr.listxattr returns list of str
                attrs = xattr.listxattr(path)  # type: ignore[attr-defined]
                for attr in attrs:
                    attr_name = attr.decode("utf-8") if isinstance(attr, bytes) else str(attr)
                    try:
                        val = xattr.getxattr(path, attr_name)  # type: ignore[attr-defined]
                    except OSError:
                        val = b""
                    if isinstance(val, str):
                        val_bytes = val.encode("utf-8")
                    elif isinstance(val, (bytes, bytearray)):
                        val_bytes = bytes(val)
                    else:
                        val_bytes = str(val).encode("utf-8")
                    size = len(val_bytes)
                    if not any(r.name == attr_name for r in results):
                        results.append(AlternateStream(name=attr_name, size=size, xattrs={attr_name: val_bytes}))
                if results:
                    return results
            except Exception:
                pass
            # Alternative API: xattr.xattr(path).list()
            try:
                xa = xattr.xattr(path)  # type: ignore[attr-defined]
                for attr in xa.list():  # type: ignore
                    attr_name = attr.decode("utf-8") if isinstance(attr, bytes) else str(attr)
                    try:
                        val = xa.get(attr_name)  # type: ignore
                    except OSError:
                        val = b""
                    if isinstance(val, str):
                        val_bytes = val.encode("utf-8")
                    elif isinstance(val, (bytes, bytearray)):
                        val_bytes = bytes(val)
                    else:
                        val_bytes = str(val).encode("utf-8")
                    size = len(val_bytes)
                    if not any(r.name == attr_name for r in results):
                        results.append(AlternateStream(name=attr_name, size=size, xattrs={attr_name: val_bytes}))
            except Exception:
                pass
        except ImportError:
            pass

    return results


def list_alternate_streams(path: str) -> list[AlternateStream]:
    """Return alternate streams / xattrs for ``path``.

    - On Windows, uses ``FindFirstStreamW``/``FindNextStreamW`` (or
      ``ntfsutils``) and surfaces ``:Zone.Identifier`` MotW.
    - On Linux/macOS, falls back to ``os.listxattr`` / ``os.getxattr``
      (or ``xattr`` lib) and returns one :class:`AlternateStream` per xattr.

    The returned list may be empty when the filesystem does not support
    streams/xattrs or the file has none.
    """
    # Windows path first — even on Linux we check sys.platform, so this
    # branch is only taken on Windows.  Keeping it first matches the spec.
    if sys.platform == "win32" or os.name == "nt":
        win_results = _list_streams_windows(path)
        if win_results:
            return win_results
        # On Windows, also include posix xattrs if any (unlikely but harmless)
        posix_results = _list_streams_posix(path)
        # MotW already handled in win branch; just return whichever is non-empty
        if posix_results:
            return posix_results
        return win_results

    # POSIX
    return _list_streams_posix(path)
