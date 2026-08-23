import errno
import hashlib
import mmap
import os
import stat

from .logger import logger

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


def _is_sparse_file(filepath: str, file_size: int | None = None) -> bool:
    """F16: sparse detection via st_blocks*512 < st_size."""
    try:
        st = os.stat(filepath)
        size = file_size if file_size is not None else st.st_size
        if size <= 0:
            return False
        blocks = getattr(st, "st_blocks", 0)
        return (blocks * 512) < size
    except OSError:
        return False
    except Exception:
        return False


def _hash_sparse_hole_aware_single(filepath: str, algo: str, file_size: int, block_size: int, cancel_token=None) -> str | None:
    """F16: Try SEEK_HOLE/SEEK_DATA hole-aware hashing. Returns hexdigest or None to fallback.

    Hashes zeros for holes so result is identical to normal read (holes are zero-filled).
    Skips seeking through holes without reading them, which is efficient for large sparse files.
    """
    if not hasattr(os, "SEEK_HOLE") or not hasattr(os, "SEEK_DATA"):
        return None
    try:
        hasher = getattr(hashlib, algo)()
        zeros_block = b"\x00" * block_size
        with open(filepath, 'rb') as f:
            fd = f.fileno()
            _advise_willneed(fd)
            offset = 0
            while offset < file_size:
                if cancel_token and cancel_token.is_set():
                    return ""
                # Find next data offset at or after current offset
                try:
                    data_off = os.lseek(fd, offset, os.SEEK_DATA)
                except OSError as e:
                    # ENXIO (errno 6) means no data until EOF → remaining is hole
                    if e.errno == errno.ENXIO:
                        remaining = file_size - offset
                        while remaining > 0:
                            if cancel_token and cancel_token.is_set():
                                return ""
                            chunk = zeros_block[: min(block_size, remaining)]
                            hasher.update(chunk)
                            remaining -= len(chunk)
                        break
                    else:
                        return None
                # data_off may be beyond file_size if no data
                if data_off >= file_size:
                    # Hole to EOF
                    remaining = file_size - offset
                    while remaining > 0:
                        if cancel_token and cancel_token.is_set():
                            return ""
                        chunk = zeros_block[: min(block_size, remaining)]
                        hasher.update(chunk)
                        remaining -= len(chunk)
                    break
                if data_off > offset:
                    hole_len = data_off - offset
                    remaining = hole_len
                    while remaining > 0:
                        if cancel_token and cancel_token.is_set():
                            return ""
                        chunk = zeros_block[: min(block_size, remaining)]
                        hasher.update(chunk)
                        remaining -= len(chunk)
                # Now data region from data_off to next hole
                try:
                    hole_off = os.lseek(fd, data_off, os.SEEK_HOLE)
                except OSError:
                    return None
                if hole_off < 0 or hole_off > file_size:
                    hole_off = file_size
                # Clamp to file_size
                if hole_off > file_size:
                    hole_off = file_size
                to_read = hole_off - data_off
                if to_read <= 0:
                    offset = hole_off
                    continue
                f.seek(data_off)
                while to_read > 0:
                    if cancel_token and cancel_token.is_set():
                        return ""
                    chunk_size = min(block_size, to_read)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    hasher.update(data)
                    to_read -= len(data)
                    # If read less than expected (e.g., truncated), break
                    if len(data) == 0:
                        break
                offset = hole_off
            return hasher.hexdigest()
    except Exception:
        return None
    return None


def _hash_sparse_hole_aware_multi(filepath: str, algos: list[str], file_size: int, block_size: int, cancel_token=None) -> dict[str, str] | None:
    """F16 hole-aware for multiple algos. Returns dict or None to fallback."""
    if not hasattr(os, "SEEK_HOLE") or not hasattr(os, "SEEK_DATA"):
        return None
    try:
        hashers = {algo: getattr(hashlib, algo)() for algo in algos}
        zeros_block = b"\x00" * block_size
        with open(filepath, 'rb') as f:
            fd = f.fileno()
            _advise_willneed(fd)
            offset = 0
            while offset < file_size:
                if cancel_token and cancel_token.is_set():
                    return {algo: "" for algo in algos}
                try:
                    data_off = os.lseek(fd, offset, os.SEEK_DATA)
                except OSError as e:
                    if e.errno == errno.ENXIO:
                        remaining = file_size - offset
                        while remaining > 0:
                            if cancel_token and cancel_token.is_set():
                                return {algo: "" for algo in algos}
                            chunk = zeros_block[: min(block_size, remaining)]
                            for h in hashers.values():
                                h.update(chunk)
                            remaining -= len(chunk)
                        break
                    else:
                        return None
                if data_off >= file_size:
                    remaining = file_size - offset
                    while remaining > 0:
                        if cancel_token and cancel_token.is_set():
                            return {algo: "" for algo in algos}
                        chunk = zeros_block[: min(block_size, remaining)]
                        for h in hashers.values():
                            h.update(chunk)
                        remaining -= len(chunk)
                    break
                if data_off > offset:
                    hole_len = data_off - offset
                    remaining = hole_len
                    while remaining > 0:
                        if cancel_token and cancel_token.is_set():
                            return {algo: "" for algo in algos}
                        chunk = zeros_block[: min(block_size, remaining)]
                        for h in hashers.values():
                            h.update(chunk)
                        remaining -= len(chunk)
                try:
                    hole_off = os.lseek(fd, data_off, os.SEEK_HOLE)
                except OSError:
                    return None
                if hole_off < 0 or hole_off > file_size:
                    hole_off = file_size
                if hole_off > file_size:
                    hole_off = file_size
                to_read = hole_off - data_off
                if to_read <= 0:
                    offset = hole_off
                    continue
                f.seek(data_off)
                while to_read > 0:
                    if cancel_token and cancel_token.is_set():
                        return {algo: "" for algo in algos}
                    chunk_size = min(block_size, to_read)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    for h in hashers.values():
                        h.update(data)
                    to_read -= len(data)
                    if len(data) == 0:
                        break
                offset = hole_off
            return {algo: h.hexdigest() for algo, h in hashers.items()}
    except Exception:
        return None
    return None


def get_file_hash(filepath: str, algo: str = 'md5', cancel_token=None) -> str:
    """
    Calculate the hash of a file using the specified algorithm.
    Supported algorithms: md5, sha1, sha256, sha512, blake2b.

    Uses 1 MiB blocks (config-driven via hash_block_size) and mmap for files
    >16 MiB with posix_fadvise/madvise WILLNEED hints. Checks cancel_token
    per chunk and returns "" if cancelled or on I/O error. Hardened against
    SIGSEGV: validates S_ISREG, zero-length, truncation race and ensures mmap
    is closed on cancel (WITH context).

    F16: Detects sparse files via st_blocks*512 < st_size and uses SEEK_HOLE
    hole-aware hashing to avoid reading 1G holes byte-for-byte while still
    hashing zeros correctly.
    """
    if cancel_token and cancel_token.is_set():
        return ""
    if algo not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported hash algorithm: {algo}")

    hasher = getattr(hashlib, algo)()
    block_size = _get_block_size()

    # Harden: stat + S_ISREG + re-stat before mmap to handle truncation/deletion race
    try:
        st = os.stat(filepath)
        if not stat.S_ISREG(st.st_mode):
            logger.debug(f"hash non-regular file {filepath}")
            return ""
        file_size = st.st_size
    except OSError as e:
        logger.debug(f"hash OSError stat {filepath}: {e}")
        return ""

    if cancel_token and cancel_token.is_set():
        return ""
    if file_size == 0:
        return hasher.hexdigest()

    # F16 sparse hole-aware path (tries SEEK_HOLE/SEEK_DATA)
    if _is_sparse_file(filepath, file_size):
        hole_result = _hash_sparse_hole_aware_single(filepath, algo, file_size, block_size, cancel_token)
        if hole_result is not None:
            return hole_result
        # Fallback to normal path if hole-aware not supported or failed

    # Large-file mmap path — zero-copy, fewer Python iterations
    if file_size > MMAP_THRESHOLD:
        if cancel_token and cancel_token.is_set():
            return ""
        try:
            with open(filepath, 'rb') as f:
                # Re-stat after open to catch truncation/deletion between stat and open
                try:
                    fst = os.fstat(f.fileno())
                    if not stat.S_ISREG(fst.st_mode):
                        logger.debug(f"hash non-regular fd {filepath}")
                        return ""
                    fresh_size = fst.st_size
                    if fresh_size != file_size:
                        file_size = fresh_size
                        if file_size == 0:
                            return hasher.hexdigest()
                except OSError as e:
                    logger.debug(f"hash fstat fallback {filepath}: {e}")
                    pass
                _advise_willneed(f.fileno())
                try:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        _madvise_willneed(mm)
                        mmap_size = len(mm)
                        effective_size = min(file_size, mmap_size) if mmap_size else file_size
                        for offset in range(0, effective_size, block_size):
                            if cancel_token and cancel_token.is_set():
                                return ""
                            end = offset + block_size
                            if end > effective_size:
                                end = effective_size
                            hasher.update(mm[offset:end])
                        return hasher.hexdigest()
                except (OSError, ValueError) as e:
                    logger.debug(f"mmap fallback {filepath}: {e}")
                    pass
        except OSError as e:
            logger.debug(f"hash OSError open {filepath}: {e}")
            return ""

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
    except OSError as e:
        logger.debug(f"hash OSError read {filepath}: {e}")
        return ""


def get_hashes(filepath: str, algos: list[str], cancel_token=None) -> dict[str, str]:
    """Calculate multiple hashes in one pass (single read, many digests). F16 sparse-aware. Hardened."""
    if cancel_token and cancel_token.is_set():
        return {algo: "" for algo in algos} if algos else {}
    for algo in algos:
        if algo not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported hash algorithm: {algo}")

    hashers = {algo: getattr(hashlib, algo)() for algo in algos}
    if not hashers:
        return {}

    block_size = _get_block_size()

    try:
        st = os.stat(filepath)
        if not stat.S_ISREG(st.st_mode):
            logger.debug(f"hashes non-regular file {filepath}")
            return {algo: "" for algo in algos}
        file_size = st.st_size
    except OSError as e:
        logger.debug(f"hashes OSError stat {filepath}: {e}")
        return {algo: "" for algo in algos}

    if cancel_token and cancel_token.is_set():
        return {algo: "" for algo in algos}
    if file_size == 0:
        return {algo: h.hexdigest() for algo, h in hashers.items()}

    # F16 sparse hole-aware multi
    if _is_sparse_file(filepath, file_size):
        hole_result = _hash_sparse_hole_aware_multi(filepath, algos, file_size, block_size, cancel_token)
        if hole_result is not None:
            return hole_result

    if file_size > MMAP_THRESHOLD:
        if cancel_token and cancel_token.is_set():
            return {algo: "" for algo in algos}
        try:
            with open(filepath, 'rb') as f:
                try:
                    fst = os.fstat(f.fileno())
                    if not stat.S_ISREG(fst.st_mode):
                        logger.debug(f"hashes non-regular fd {filepath}")
                        return {algo: "" for algo in algos}
                    fresh_size = fst.st_size
                    if fresh_size != file_size:
                        file_size = fresh_size
                        if file_size == 0:
                            return {algo: h.hexdigest() for algo, h in hashers.items()}
                except OSError as e:
                    logger.debug(f"hashes fstat fallback {filepath}: {e}")
                    pass
                _advise_willneed(f.fileno())
                try:
                    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                        _madvise_willneed(mm)
                        mmap_size = len(mm)
                        effective_size = min(file_size, mmap_size) if mmap_size else file_size
                        for offset in range(0, effective_size, block_size):
                            if cancel_token and cancel_token.is_set():
                                return {algo: "" for algo in algos}
                            end = offset + block_size
                            if end > effective_size:
                                end = effective_size
                            chunk = mm[offset:end]
                            for h in hashers.values():
                                h.update(chunk)
                        return {algo: h.hexdigest() for algo, h in hashers.items()}
                except (OSError, ValueError) as e:
                    logger.debug(f"hashes mmap fallback {filepath}: {e}")
                    pass
        except OSError as e:
            logger.debug(f"hashes OSError open {filepath}: {e}")
            return {algo: "" for algo in algos}

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
    except OSError as e:
        logger.debug(f"hashes OSError read {filepath}: {e}")
        return {algo: "" for algo in algos}
