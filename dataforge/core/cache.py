import sqlite3
import os
import threading
from pathlib import Path
from typing import List

from .logger import logger

# ---------------------------------------------------------------------------
# Schema versioning — INSTALL_UPGRADE_LIFECYCLE §7.2
# ---------------------------------------------------------------------------
CACHE_SCHEMA_VERSION: int = 2

# Migrations live under dataforge/engine/migrations/*.sql (Wave 0 contract:
# directory exists, not yet populated; Wave 1 (TICK-104) fills impl).
MIGRATIONS_DIR: Path = Path(__file__).resolve().parent.parent / "engine" / "migrations"


class CacheManager:
    def __init__(self, db_path=None):
        if not db_path:
            try:
                from .paths import cache_db as _pdb

                db_path = str(_pdb)
            except ImportError:
                try:
                    from dataforge.core.paths import cache_db as _pdb2

                    db_path = str(_pdb2)
                except ImportError:
                    db_path = os.path.join(os.path.expanduser("~"), ".dataforge", "cache.db")

        self.db_path = db_path
        self.conn = None
        self._lock = threading.RLock()
        self._batch_buffer: List[tuple[str, int, float, str, str]] = []
        self._batch_size_val: int = 1000
        self._user_version: int = 0
        self._pending_migrations: List[Path] = []
        self._init_db()
        # initialise batch size from config (if available)
        try:
            self._batch_size_val = self._get_batch_size()
        except Exception:
            pass

    def _init_db(self):
        try:
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.Error:
                pass
            try:
                self.conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.Error:
                pass
            try:
                self.conn.execute("PRAGMA cache_size=-64000")
            except sqlite3.Error:
                pass
            try:
                self.conn.execute("PRAGMA busy_timeout=30000")
            except sqlite3.Error:
                pass
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS file_hashes (
                    path TEXT PRIMARY KEY,
                    size INTEGER,
                    mtime REAL,
                    hash TEXT,
                    algo TEXT
                )
            """)
            try:
                self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_hash_lookup ON file_hashes(algo, size, mtime)"
                )
            except sqlite3.Error:
                pass
            self.conn.commit()
            try:
                cur = self.conn.execute("PRAGMA user_version")
                row = cur.fetchone()
                self._user_version = int(row[0]) if row and row[0] is not None else 0
            except sqlite3.Error:
                self._user_version = 0
            self._pending_migrations = self.get_pending_migrations()
        except sqlite3.Error as e:
            logger.error(f"Failed to init cache DB: {e}")

    def get_user_version(self) -> int:
        return self._user_version

    def get_pending_migrations(self) -> List[Path]:
        try:
            if not MIGRATIONS_DIR.exists():
                return []
            if self._user_version >= CACHE_SCHEMA_VERSION:
                return []
            sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            return sql_files
        except Exception:
            return []

    @property
    def pending_migrations(self) -> List[Path]:
        fresh = self.get_pending_migrations()
        if fresh != self._pending_migrations:
            self._pending_migrations = fresh
        return self._pending_migrations

    # --- Batch helpers (R-CORE-5) ---
    def _get_batch_size(self) -> int:
        try:
            from .config import config

            v = config.get("cache_batch_size", 1000)
            if isinstance(v, int) and 1 <= v <= 100000:
                return v
        except Exception:
            pass
        return getattr(self, "_batch_size_val", 1000)

    @property
    def _batch_size(self) -> int:
        return getattr(self, "_batch_size_val", 1000)

    @_batch_size.setter
    def _batch_size(self, value: int) -> None:
        if isinstance(value, int) and 1 <= value <= 100000:
            self._batch_size_val = int(value)
        elif value is None:
            self._batch_size_val = 1000
        else:
            # allow any int, clamp to 1..100000 for safety
            try:
                iv = int(value)  # type: ignore[arg-type]
                if 1 <= iv <= 100000:
                    self._batch_size_val = iv
                else:
                    self._batch_size_val = 1000
            except Exception:
                self._batch_size_val = 1000

    def _flush_batch_locked(self) -> None:
        """Flush pending batch buffer; caller must hold _lock."""
        if not self._batch_buffer:
            return
        if self.conn is None:
            self._batch_buffer.clear()
            return
        rows = list(self._batch_buffer)
        self._batch_buffer.clear()
        try:
            self.conn.executemany(
                "INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash, algo) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
            self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to batch cache hashes: {e}")

    def flush(self) -> None:
        """Flush any buffered set_hash writes."""
        if self.conn is None:
            with self._lock:
                self._batch_buffer.clear()
            return None
        with self._lock:
            self._flush_batch_locked()
        return None

    def get_hash(self, path, size, mtime, algo='md5'):
        if self.conn is None:
            return None
        with self._lock:
            # Check buffered writes first (most recent wins)
            for b_path, b_size, b_mtime, b_hash, b_algo in reversed(self._batch_buffer):
                if b_path == path and b_size == size and b_mtime == mtime and b_algo == algo:
                    return b_hash
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT hash FROM file_hashes WHERE path=? AND size=? AND mtime=? AND algo=?",
                (path, size, mtime, algo)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_hash(self, path, size, mtime, hash_val, algo='md5'):
        if self.conn is None:
            return None
        try:
            with self._lock:
                self._batch_buffer.append((path, size, mtime, hash_val, algo))
                if len(self._batch_buffer) >= self._batch_size:
                    self._flush_batch_locked()
        except sqlite3.Error as e:
            logger.error(f"Failed to cache hash for {path}: {e}")
        return None

    def set_hash_many(self, rows: List[tuple[str, int, float, str, str]]) -> None:
        if self.conn is None:
            return None
        if not isinstance(rows, list):
            raise TypeError("rows must be a list of tuples")
        for idx, row in enumerate(rows):
            if not isinstance(row, (list, tuple)):
                raise TypeError(f"row {idx} must be tuple/list, got {type(row).__name__}")
            if len(row) != 5:
                raise ValueError(f"row {idx} must have 5 elements (path,size,mtime,hash,algo), got {len(row)}")
            path, size, mtime, hash_val, algo = row
            if not isinstance(path, str):
                raise TypeError(f"row {idx} path must be str, got {type(path).__name__}")
            if not isinstance(size, int):
                raise TypeError(f"row {idx} size must be int, got {type(size).__name__}")
            if not isinstance(mtime, (int, float)):
                raise TypeError(f"row {idx} mtime must be int|float, got {type(mtime).__name__}")
            if not isinstance(hash_val, str):
                raise TypeError(f"row {idx} hash must be str, got {type(hash_val).__name__}")
            if not isinstance(algo, str):
                raise TypeError(f"row {idx} algo must be str, got {type(algo).__name__}")
        if not rows:
            return None
        try:
            with self._lock:
                self.conn.executemany(
                    "INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash, algo) VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to batch cache hashes: {e}")
        return None

    def clear(self):
        if self.conn is None:
            with self._lock:
                self._batch_buffer.clear()
            return
        try:
            with self._lock:
                self._batch_buffer.clear()
                self.conn.execute("DELETE FROM file_hashes")
                self.conn.commit()
                old_iso = self.conn.isolation_level
                self.conn.isolation_level = None
                try:
                    self.conn.execute("VACUUM")
                finally:
                    self.conn.isolation_level = old_iso
            logger.info("Cache cleared successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to clear cache: {e}")

    def close(self):
        with self._lock:
            try:
                self._flush_batch_locked()
            except Exception:
                pass
            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None

file_cache = CacheManager()
