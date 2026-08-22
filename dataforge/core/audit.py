"""
Hash-chained audit log for forensic soundness (F1/F11).

Append-only SQLite WAL database with hash(prev || canonical_json) chain.
Each entry is tamper-evident: modifying any byte in the chain invalidates
all subsequent hashes.  File permissions are 0o600.

Addresses FORENSIC_REVIEW F1 (chain-of-custody) and F11 (app.log not
hash-chained).
"""
import hashlib
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional


_DEFAULT_DB_PATH = os.path.join(
    os.path.expanduser("~"), ".dataforge", "audit.db"
)

_lock = threading.Lock()


def _canonical_json(payload: dict) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash_chain(prev_hash: str, canonical: str) -> str:
    """SHA-256(prev_hash || canonical_json)."""
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class AuditLog:
    """Append-only, hash-chained audit log backed by SQLite WAL.

    Each row: (id, timestamp_utc, action, payload_json, entry_hash, prev_hash).
    The chain starts with a genesis entry whose prev_hash is "0" * 64.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_db()

    # -- lifecycle -----------------------------------------------------------

    def _ensure_db(self) -> None:
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        # Create with 0o600 if new
        if not os.path.exists(self._db_path):
            fd = os.open(self._db_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                action      TEXT    NOT NULL,
                payload_json TEXT   NOT NULL,
                entry_hash  TEXT    NOT NULL,
                prev_hash   TEXT    NOT NULL
            )
            """
        )
        self._conn.commit()
        # Ensure 0o600 on existing file
        try:
            os.chmod(self._db_path, 0o600)
        except OSError:
            pass

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- internal helpers ----------------------------------------------------

    def _last_hash(self) -> str:
        """Return the hash of the most recent entry, or GENESIS_HASH if empty."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else self.GENESIS_HASH

    # -- public API ----------------------------------------------------------

    def append(self, action: str, payload: dict) -> dict:
        """Append an entry to the audit chain.

        Returns the inserted row as a dict (id, timestamp, action, payload,
        entry_hash, prev_hash).
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        full_payload = {"action": action, "timestamp": timestamp, **payload}
        canonical = _canonical_json(full_payload)

        with _lock:
            prev_hash = self._last_hash()
            entry_hash = _hash_chain(prev_hash, canonical)
            assert self._conn is not None
            self._conn.execute(
                "INSERT INTO audit_log (timestamp, action, payload_json, entry_hash, prev_hash) VALUES (?, ?, ?, ?, ?)",
                (timestamp, action, canonical, entry_hash, prev_hash),
            )
            self._conn.commit()
            row_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        return {
            "id": row_id,
            "timestamp": timestamp,
            "action": action,
            "payload": full_payload,
            "entry_hash": entry_hash,
            "prev_hash": prev_hash,
        }

    def verify(self) -> dict:
        """Walk the entire chain and verify hash integrity.

        Returns {"valid": bool, "entries_checked": int, "first_bad_id": int|None}.
        """
        with _lock:
            assert self._conn is not None
            rows = self._conn.execute(
                "SELECT id, timestamp, action, payload_json, entry_hash, prev_hash "
                "FROM audit_log ORDER BY id ASC"
            ).fetchall()

        prev = self.GENESIS_HASH
        for row_id, _ts, _action, payload_json, entry_hash, prev_hash in rows:
            if prev_hash != prev:
                return {"valid": False, "entries_checked": row_id, "first_bad_id": row_id}
            expected = _hash_chain(prev_hash, payload_json)
            if expected != entry_hash:
                return {"valid": False, "entries_checked": row_id, "first_bad_id": row_id}
            prev = entry_hash

        return {"valid": True, "entries_checked": len(rows), "first_bad_id": None}

    def tail_hash(self) -> str:
        """Return the hash of the latest entry (the 'audit tail')."""
        with _lock:
            return self._last_hash()

    def count(self) -> int:
        """Return total number of entries."""
        with _lock:
            assert self._conn is not None
            row = self._conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()
            return row[0] if row else 0

    def get_entries(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Return recent entries as a list of dicts."""
        with _lock:
            assert self._conn is not None
            rows = self._conn.execute(
                "SELECT id, timestamp, action, payload_json, entry_hash, prev_hash "
                "FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        return [
            {
                "id": row_id,
                "timestamp": ts,
                "action": action,
                "payload": json.loads(payload_json),
                "entry_hash": entry_hash,
                "prev_hash": prev_hash,
            }
            for row_id, ts, action, payload_json, entry_hash, prev_hash in rows
        ]
