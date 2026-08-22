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
        self._lock = threading.Lock()
        self._user_version: int = 0
        self._pending_migrations: List[Path] = []
        self._init_db()

    def _init_db(self):
        try:
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
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

    def get_hash(self, path, size, mtime, algo='md5'):
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT hash FROM file_hashes WHERE path=? AND size=? AND mtime=? AND algo=?",
                (path, size, mtime, algo)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_hash(self, path, size, mtime, hash_val, algo='md5'):
        try:
            with self._lock:
                self.conn.execute(
                    "INSERT OR REPLACE INTO file_hashes (path, size, mtime, hash, algo) VALUES (?, ?, ?, ?, ?)",
                    (path, size, mtime, hash_val, algo)
                )
                self.conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to cache hash for {path}: {e}")

    def set_hash_many(self, rows: List[tuple[str, int, float, str, str]]) -> None:
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
        return None

    def clear(self):
        try:
            with self._lock:
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
            if self.conn:
                self.conn.close()

file_cache = CacheManager()
