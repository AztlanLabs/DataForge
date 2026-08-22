"""File-provider abstraction — DataForge's seam to the filesystem.

TICK-002 expanded contract (docs/proposals/NATIVE_OS_API_REVIEW.md §3.3,
docs/PARALLEL_BACKLOG.md TICK-002): seven filesystem access methods, all
taking an optional cooperative ``cancel_token`` plus a progress callback
wherever work is incremental. ``LocalProvider`` remains a thin shim over
the existing scanner/hasher contracts; alternate backends (mounted image,
SSH, S3) implement the same interface behind the future engine.
"""

import os
import shutil
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import IO, Optional

from .common import FileEntry

#: Cooperative cancellation handle accepted by every provider call.
CancelToken = Optional[threading.Event]

#: ``progress_callback(done, total)``; ``total`` is -1 while unknown.
ProgressCallback = Optional[Callable[[int, int], None]]


class FileProvider(ABC):
    """Abstract filesystem backend.

    Contract (TICK-002):

    - Every traversal/read method accepts ``cancel_token`` checked between
      units of work, and the incremental ones also accept
      ``progress_callback(done, total)``.
    - Only the pre-existing trio ``list_files`` / ``move`` / ``copy`` is
      abstract. The new methods (``list_files_parallel``, ``stat``,
      ``open``, ``hash``, ``hash_many``, ``exists``) carry default shims so
      subclasses written against the original three-method ABC remain
      instantiable; derived operations (``list_files_parallel``,
      ``hash_many``, ``exists``) fall back to their primitive counterparts.
    """

    @abstractmethod
    def list_files(
        self,
        path: str,
        recursive: bool = True,
        cancel_token: CancelToken = None,
        progress_callback: ProgressCallback = None,
    ) -> Iterable[FileEntry]:
        """Yield :class:`FileEntry` objects for the files under ``path``."""
        raise NotImplementedError

    def list_files_parallel(
        self,
        root: str,
        cancel_token: CancelToken = None,
        progress_callback: ProgressCallback = None,
    ) -> Iterable[FileEntry]:
        """Yield entries using parallel descent when a backend has one.

        Default shim delegates to :meth:`list_files`; the local parallel
        BFS walker lands with the TICK-102 scanner contract.
        """
        return self.list_files(root, recursive=True, cancel_token=cancel_token, progress_callback=progress_callback)

    def stat(self, path: str, cancel_token: CancelToken = None) -> os.stat_result:
        """Return ``os.stat``-style metadata; raises OSError if missing."""
        raise NotImplementedError

    def open(self, path: str, mode: str = "rb", cancel_token: CancelToken = None) -> IO[bytes]:
        """Open ``path`` for I/O; raises OSError on failure."""
        raise NotImplementedError

    def hash(
        self,
        path: str,
        algo: str = "sha256",
        cancel_token: CancelToken = None,
        progress_callback: ProgressCallback = None,
    ) -> str:
        """Return the hex digest of ``path`` ("" on failure or cancel)."""
        raise NotImplementedError

    def hash_many(
        self,
        paths: list[str],
        algo: str = "sha256",
        cancel_token: CancelToken = None,
        progress_callback: ProgressCallback = None,
    ) -> dict[str, str]:
        """Hash several files, mapping every input path to its digest.

        Default shim loops over :meth:`hash`. Cancelled or unreadable
        paths map to "" so the result always covers all inputs.
        """
        digests: dict[str, str] = {}
        total = len(paths)
        done = 0
        for file_path in paths:
            if file_path in digests:
                continue
            cancelled = cancel_token is not None and cancel_token.is_set()
            digests[file_path] = "" if cancelled else self.hash(file_path, algo, cancel_token)
            done += 1
            if progress_callback is not None:
                progress_callback(done, total)
        return digests

    def exists(self, path: str, cancel_token: CancelToken = None) -> bool:
        """True if ``path`` exists; also False when cancelled."""
        if cancel_token is not None and cancel_token.is_set():
            return False
        try:
            self.stat(path, cancel_token=cancel_token)
        except OSError:
            return False
        return True

    @abstractmethod
    def move(self, src: str, dst: str):
        pass

    @abstractmethod
    def copy(self, src: str, dst: str):
        pass


class LocalProvider(FileProvider):
    """Thin shim wiring the ABC onto the local scanner/hasher/os stack."""

    def list_files(
        self,
        path: str,
        recursive: bool = True,
        cancel_token: CancelToken = None,
        progress_callback: ProgressCallback = None,
    ) -> Iterable[FileEntry]:
        from .scanner import scan_directory

        done = 0
        for entry in scan_directory(path, recursive, cancel_token=cancel_token):
            yield entry
            done += 1
            if progress_callback is not None:
                progress_callback(done, -1)

    def stat(self, path: str, cancel_token: CancelToken = None) -> os.stat_result:
        return os.stat(path)

    def open(self, path: str, mode: str = "rb", cancel_token: CancelToken = None) -> IO[bytes]:
        return open(path, mode)

    def hash(
        self,
        path: str,
        algo: str = "sha256",
        cancel_token: CancelToken = None,
        progress_callback: ProgressCallback = None,
    ) -> str:
        from .hasher import get_file_hash

        return get_file_hash(path, algo, cancel_token)

    def move(self, src: str, dst: str):
        shutil.move(src, dst)

    def copy(self, src: str, dst: str):
        shutil.copy2(src, dst)


def default_provider() -> FileProvider:
    """Provider used when no backend is selected — always ``LocalProvider``.

    Backend selection (image/SSH/S3) lands with the engine; until then
    callers that skip provider choice get unchanged local-disk behavior.
    """
    return LocalProvider()
