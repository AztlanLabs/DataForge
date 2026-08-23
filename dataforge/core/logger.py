import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class ChainToAuditFilter(logging.Filter):
    """Forwards >=INFO records into AuditLog hash chain when enabled.

    When ``chain_to_audit`` is True and Evidence Mode is active and
    ``DATAFORGE_CHAIN_APP_LOG`` is not ``"0"``, every ``>=INFO`` record is
    also appended to ``AuditLog`` as ``event='log'``. The chain itself is
    computed by :class:`dataforge.core.audit.AuditLog` (SHA-256(prev ||
    canonical_json)), so ``audit.verify()`` detects tampering for log entries
    as well as forensic events. When the flag is False (default) the logger
    behaves exactly as before — no extra DB writes.
    """

    def __init__(self, name: str = "", audit_log=None):
        super().__init__(name)
        self._audit_log = audit_log
        self._audit_cls = None
        if audit_log is None:
            try:
                from .audit import AuditLog as _AuditLog

                self._audit_cls = _AuditLog
            except Exception:
                self._audit_cls = None

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: N802
        # Always allow record to propagate to handlers.
        if record.levelno < logging.INFO:
            return True
        if os.environ.get("DATAFORGE_CHAIN_APP_LOG") == "0":
            return True
        try:
            from .case import is_evidence_mode

            if not is_evidence_mode():
                return True
        except Exception:
            return True
        # Build payload and forward to AuditLog.
        try:
            audit = self._audit_log
            if audit is None and self._audit_cls is not None:
                try:
                    audit = self._audit_cls()
                except Exception:
                    return True
                # Cache for subsequent records (still respects monkeypatch via class lookup)
                self._audit_log = audit
            if audit is None:
                return True
            msg = record.getMessage()
            try:
                ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
            except Exception:
                ts = datetime.now(timezone.utc).isoformat()
            payload = {
                "event": "log",
                "level": record.levelname,
                "name": record.name,
                "msg": msg,
                "args": str(record.args) if record.args else "",
                "exc_info": str(record.exc_info) if record.exc_info else "",
                "ts": ts,
            }
            # AuditLog.append(action, payload) — action is 'log', payload contains event='log'
            audit.append("log", payload)
        except Exception:
            # Never block logging on audit failure.
            pass
        return True


def setup_logger(
    name: str = "dataforge",
    log_file: str | None = None,
    level: int = logging.INFO,
    chain_to_audit: bool = False,
    audit_log=None,
):
    """
    Configure and return a standard logger.

    When ``chain_to_audit`` is True the logger also forwards ``>=INFO`` records
    into the hash-chained :class:`dataforge.core.audit.AuditLog` via
    :class:`ChainToAuditFilter`. The filter is only effective when Evidence Mode
    is active (``CaseContext.is_evidence_mode()``) and ``DATAFORGE_CHAIN_APP_LOG``
    is not ``"0"``. Defaults to False for test-suite ergonomics.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if setup called multiple times —
    # but still reconcile chain_to_audit filter parity.
    if logger.handlers:
        has_filter = any(isinstance(f, ChainToAuditFilter) for f in logger.filters)
        if chain_to_audit and not has_filter:
            # Only wire if conditions allow at least at filter-time; filter itself
            # re-checks evidence mode + env on each record so dynamic toggling works.
            try:
                if os.environ.get("DATAFORGE_CHAIN_APP_LOG") != "0":
                    logger.addFilter(ChainToAuditFilter(audit_log=audit_log))
            except Exception:
                pass
        elif not chain_to_audit and has_filter:
            for f in list(logger.filters):
                if isinstance(f, ChainToAuditFilter):
                    try:
                        logger.removeFilter(f)
                    except Exception:
                        pass
        # Also handle audit_log injection update if filter already exists and new audit_log provided
        elif chain_to_audit and has_filter and audit_log is not None:
            for f in logger.filters:
                if isinstance(f, ChainToAuditFilter):
                    try:
                        f._audit_log = audit_log
                        if audit_log is not None:
                            f._audit_cls = None
                    except Exception:
                        pass
        return logger

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console Handler — routed to stderr so CLI JSON on stdout stays clean (R-CORE-1)
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Normalize empty/whitespace log_file to fallback (R-CORE-7)
    if isinstance(log_file, str) and not log_file.strip():
        try:
            _fallback = globals().get("default_log_path")
            if not _fallback:
                _fallback = os.path.join(os.path.expanduser("~"), ".dataforge", "app.log")
        except Exception:
            _fallback = os.path.join(os.path.expanduser("~"), ".dataforge", "app.log")
        log_file = _fallback

    # File Handler
    if log_file:
        _dirname = os.path.dirname(log_file) if log_file else ""
        _should_add_file_handler = True
        if _dirname:
            try:
                os.makedirs(_dirname, exist_ok=True)
            except OSError as e:
                _should_add_file_handler = False
                try:
                    logger.warning("Could not create log dir %s: %s", _dirname, e)
                except Exception:
                    pass
        if _should_add_file_handler:
            try:
                # Ensure file exists with 0o600 before handler opens it (handler creates file on first emit)
                if not os.path.exists(log_file):
                    try:
                        fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                        os.close(fd)
                    except OSError:
                        pass
                fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
                fh.setLevel(level)
                fh.setFormatter(formatter)
                logger.addHandler(fh)
                try:
                    os.chmod(log_file, 0o600)
                except OSError:
                    pass
            except OSError as e:
                try:
                    logger.warning("Could not create log file %s: %s", log_file, e)
                except Exception:
                    pass

    # Chain filter — only when explicitly opted-in. The filter itself checks
    # Evidence Mode and DATAFORGE_CHAIN_APP_LOG at record time so that
    # toggling evidence mode after setup is still respected.
    if chain_to_audit:
        try:
            if os.environ.get("DATAFORGE_CHAIN_APP_LOG") != "0":
                logger.addFilter(ChainToAuditFilter(audit_log=audit_log))
        except Exception:
            pass

    return logger


# Default instance
# We can determine a default log path (e.g. ~/.dataforge/app.log)
default_log_path = os.path.join(os.path.expanduser("~"), ".dataforge", "app.log")
logger = setup_logger("dataforge", default_log_path)
