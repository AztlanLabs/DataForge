import hashlib
import mmap
import os

# Block size is config-driven (1 MiB) — TICK-004 adds hash_block_size to config.
# Fallback to 1<<20 if config not yet loaded or import fails (e.g., during tests
# that set DATAFORGE_SKIP_LEGACY_MIGRATION). Keep public BLOCK_SIZE for compat.
_DEFAULT_BLOCK_SIZE = 1 << 20
MMAP_THRESHOLD = 16 * 1024 * 1024  # 16 MiB — use mmap above this size


def _get_block_size() -> int:
    """Return the configured hash block size, falling back to 1 MiB."""
    try:
        from .config import config as _cfg

        v = _cfg.get("hash_block_size", _DEFAULT_BLOCK_SIZE)
        if isinstance(v, int) and 1024 <= v <= 16 * 1024 * 1024:
            return v
    except Exception:
        pass
    return _DEFAULT_BLOCK_SIZE


# Public constant — evaluated at import time but re-read dynamically per call
# via _get_block_size() so runtime config changes are honoured.
try:
    BLOCK_SIZE = _get_block_size()
except Exception:
    BLOCK_SIZE = _DEFAULT_BLOCK_SIZE

# Digest algorithms the app supports everywhere (CLI, GUI, forensics, integrity).
SUPPORTED_ALGORITHMS = ('md5', 'sha1', 'sha256', 'sha512', 'blake2b')


def _advise_willneed(fd: int) -> None:
    """Hint the kernel to prefetch file pages (Linux posix_fadvise)."""
    try:
        if hasattr(os, 'posix_fadvise'):
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_WILLNEED)
    except OSError:
        pass


def _madvise_willneed(mm: mmap.mmap) -> None:
    """Hint the kernel to prefetch mmap pages (madvise WILLNEED)."""
    try:
        if hasattr(mmap, 'MADV_WILLNEED'):
            mm.madvise(mmap.MADV_WILLNEED)
    except Exception:
        pass


def get_file_hash(filepath: str, algo: str = 'md5', cancel_token=None) -> str:
    """
    Calculate the hash of a file using the specified algorithm.
    Supported algorithms: md5, sha1, sha256, sha512, blake2b.

    Uses 1 MiB blocks (config-driven via hash_block_size) and mmap for files
    >16 MiB with posix_fadvise/madvise WILLNEED hints. Checks cancel_token
    per chunk and returns "" if cancelled or on I/O error.
    """
    if algo not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported hash algorithm: {algo}")

    hasher = getattr(hashlib, algo)()
    block_size = _get_block_size()

    # Fast stat for size / empty-file handling
    try:
        file_size = os.path.getsize(filepath)
    except OSError:
        return ""

    if file_size == 0:
        if cancel_token and cancel_token.is_set():
            return ""
        return hasher.hexdigest()

    # Large-file mmap path — zero-copy, fewer Python iterations
    if file_size > MMAP_THRESHOLD:
        try:
            with open(filepath, 'rb') as f:
                _advise_willneed(f.fileno())
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    _madvise_willneed(mm)
                    for offset in range(0, file_size, block_size):
                        if cancel_token and cancel_token.is_set():
                            return ""
                        end = offset + block_size
                        if end > file_size:
                            end = file_size
                        hasher.update(mm[offset:end])
                    return hasher.hexdigest()
        except (OSError, ValueError):
            # mmap can fail on special files / empty / no support — fall back
            pass

    try:
        with open(filepath, 'rb') as f:
            _advise_willneed(f.fileno())
            while True:
                if cancel_token and cancel_token.is_set():
                    return ""
                data = f.read(block_size)
                if not data:
                    break
                hasher.update(data)
        return hasher.hexdigest()
    except OSError:
        return ""


def get_hashes(filepath: str, algos: list[str], cancel_token=None) -> dict[str, str]:
    """Calculate multiple hashes in one pass (single read, many digests)."""
    for algo in algos:
        if algo not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported hash algorithm: {algo}")

    hashers = {algo: getattr(hashlib, algo)() for algo in algos}
    if not hashers:
        return {}

    block_size = _get_block_size()

    try:
        file_size = os.path.getsize(filepath)
    except OSError:
        return {algo: "" for algo in algos}

    if file_size == 0:
        if cancel_token and cancel_token.is_set():
            return {algo: "" for algo in algos}
        return {algo: h.hexdigest() for algo, h in hashers.items()}

    if file_size > MMAP_THRESHOLD:
        try:
            with open(filepath, 'rb') as f:
                _advise_willneed(f.fileno())
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    _madvise_willneed(mm)
                    for offset in range(0, file_size, block_size):
                        if cancel_token and cancel_token.is_set():
                            return {algo: "" for algo in algos}
                        end = offset + block_size
                        if end > file_size:
                            end = file_size
                        chunk = mm[offset:end]
                        for h in hashers.values():
                            h.update(chunk)
                    return {algo: h.hexdigest() for algo, h in hashers.items()}
        except (OSError, ValueError):
            pass

    try:
        with open(filepath, 'rb') as f:
            _advise_willneed(f.fileno())
            while True:
                if cancel_token and cancel_token.is_set():
                    return {algo: "" for algo in algos}
                data = f.read(block_size)
                if not data:
                    break
                for h in hashers.values():
                    h.update(data)
        return {algo: h.hexdigest() for algo, h in hashers.items()}
    except OSError:
        return {algo: "" for algo in algos}
