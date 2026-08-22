"""
Case context for forensic operations (F2/U1/U2).

Carries case ID, operator, host, source image hash, and an evidence_mode
flag that gates destructive operations via FileActionService.

Addresses FORENSIC_REVIEW F2 (acquisition provenance), U1 (no case/
evidence/operator context), and U2 (no EVIDENCE MODE toggle).
"""
import platform
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CaseContext:
    """Immutable case metadata + evidence-mode gate.

    Fields:
        case_id:      Unique case identifier (e.g. "CASE-2026-0001").
        operator:     Name or ID of the investigating operator.
        host:         Machine hostname where the analysis runs.
        source_sha256: SHA-256 of the source evidence image (if known).
        evidence_mode: When True, destructive operations are blocked.
    """

    case_id: str = ""
    operator: str = ""
    host: str = field(default_factory=platform.node)
    source_sha256: str = ""
    evidence_mode: bool = False

    def __post_init__(self) -> None:
        if not self.host:
            self.host = platform.node() or "unknown"

    def to_dict(self) -> dict:
        """Serialize for embedding in reports and audit entries."""
        return {
            "case_id": self.case_id,
            "operator": self.operator,
            "host": self.host,
            "source_sha256": self.source_sha256,
            "evidence_mode": self.evidence_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CaseContext":
        """Deserialize from a dict."""
        return cls(
            case_id=data.get("case_id", ""),
            operator=data.get("operator", ""),
            host=data.get("host", platform.node() or "unknown"),
            source_sha256=data.get("source_sha256", ""),
            evidence_mode=data.get("evidence_mode", False),
        )


# ---------------------------------------------------------------------------
# Module-level singleton (thread-safe)
# ---------------------------------------------------------------------------
_global_context: Optional[CaseContext] = None
_context_lock = threading.Lock()


def get_context() -> Optional[CaseContext]:
    """Return the current global CaseContext, or None if unset."""
    return _global_context


def set_context(ctx: CaseContext) -> None:
    """Set the global CaseContext (thread-safe)."""
    global _global_context
    with _context_lock:
        _global_context = ctx


def clear_context() -> None:
    """Reset the global CaseContext to None (thread-safe)."""
    global _global_context
    with _context_lock:
        _global_context = None


def is_evidence_mode() -> bool:
    """Convenience: True when a CaseContext is active with evidence_mode=True."""
    ctx = _global_context
    return ctx is not None and ctx.evidence_mode
