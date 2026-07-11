import sqlite3
import os
import threading
from .logger import logger
from .config import config

class CacheManager:
    def __init__(self, db_path=None):
        if not db_path:
            db_path = os.path.join(os.path.expanduser("~"), ".filemanager", "cache.db")

        self.db_path = db_path
        self.conn = None
        # The single connection is shared across BackgroundWorker(QThread)s, so
        # every access is serialized through this lock. Without it, concurrent
        # workers (or a VACUUM racing in-flight cursors) can raise
        # "database is locked" / "recursive use of cursors".
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # WAL improves concurrent read/write behaviour for the shared conn.
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
        except sqlite3.Error as e:
            logger.error(f"Failed to init cache DB: {e}")

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

    def clear(self):
        """Clear all cached hashes."""
        try:
            with self._lock:
                self.conn.execute("DELETE FROM file_hashes")
                self.conn.commit() # Commit delete first

                # VACUUM cannot be run inside a transaction.
                # Ensure isolation is auto-commit or just clean state.
                old_iso = self.conn.isolation_level
                self.conn.isolation_level = None # Autocommit mode
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

# Global cache
file_cache = CacheManager()
