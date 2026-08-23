"""Hardening for NTFS/fuse filesystem corruption on importlib.metadata.

On external NTFS mounts (e.g. /run/media/... fuseblk), .dist-info directories
can become unreadable with Input/output error (Errno 5) on individual files
like entry_points.txt / METADATA. Python's importlib.metadata.distributions()
iterates all distributions and pydantic eagerly loads entry_points during model
construction (BaseModel -> plugin loader -> entry_points()). A single corrupted
.dist-info then crashes the entire app at import time (see run_ui.py traceback).

This module monkey-patches importlib.metadata to tolerate OSError on a single
distribution: the corrupted dist is skipped with a one-time warning, all other
dists are yielded normally. It is idempotent and must be imported before any
`pydantic.BaseModel` subclass is defined.

Include this as the very first import in:
  - run_ui.py
  - dataforge/__init__.py  (covers all `import dataforge.*` paths)
  - dataforge/api/schema.py  (defines Pydantic models)

The patch is intentionally tiny, has no deps, and never raises.
"""

from __future__ import annotations

import importlib.metadata as _im

_patched = False
_original_distributions = _im.distributions
_original_entry_points = _im.entry_points

try:
    _PathDistribution = _im.PathDistribution  # Python 3.10+ has this in importlib.metadata
except AttributeError:
    _PathDistribution = None  # type: ignore[assignment]


def _install() -> None:
    global _patched
    if _patched:
        return
    _patched = True

    # Patch distributions() to skip any dist whose metadata files raise OSError
    def _safe_distributions(*args, **kwargs):  # type: ignore[no-untyped-def]
        for dist in _original_distributions(*args, **kwargs):
            try:
                # Probe the file that actually failed in the traceback:
                # PathDistribution.read_text('entry_points.txt') does io.open -> OSError 5
                # If this succeeds (or dist has no entry_points.txt -> None), dist is usable.
                # Use read_text if available, else fallback to try entry_points property.
                if hasattr(dist, "read_text"):
                    try:
                        dist.read_text("entry_points.txt")
                    except FileNotFoundError:
                        pass  # no entry_points.txt is fine
                    except OSError:
                        # Corrupted dist-info — skip this dist entirely
                        _warn_once(dist, "entry_points.txt")
                        continue
                yield dist
            except OSError:
                _warn_once(dist, "distributions()")
                continue
            except Exception:
                # Be conservative: yield on unknown errors so we don't hide legit issues
                try:
                    yield dist
                except Exception:
                    continue

    # Patch entry_points() top-level to catch OSError from any single dist
    def _safe_entry_points(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return _original_entry_points(*args, **kwargs)
        except OSError as e:
            _warn_once(None, f"entry_points() OSError: {e}")
            # Return empty EntryPoints so callers (pydantic) get no plugins rather than crash
            try:
                return _im.EntryPoints([])
            except Exception:
                return []

    # Optional: also harden PathDistribution.read_text directly for any direct calls
    if _PathDistribution is not None and hasattr(_PathDistribution, "read_text"):
        _orig_read_text = _PathDistribution.read_text

        def _safe_read_text(self, filename):  # type: ignore[no-untyped-def]
            try:
                return _orig_read_text(self, filename)
            except OSError:
                # Only suppress for entry_points.txt / METADATA on corrupted NTFS;
                # re-raise for other files? For robustness, return None for any OSError here
                # because importlib.metadata callers treat None as "no such file".
                if filename in ("entry_points.txt", "METADATA", "RECORD", "WHEEL", "top_level.txt"):
                    _warn_once(self, filename)
                    return None
                raise

        _PathDistribution.read_text = _safe_read_text  # type: ignore[assignment]

    _im.distributions = _safe_distributions  # type: ignore[assignment]
    _im.entry_points = _safe_entry_points  # type: ignore[assignment]


_warned_dists: set[str] = set()


def _warn_once(dist, context: str) -> None:
    try:
        key = str(getattr(dist, "_path", dist) if dist is not None else context) + ":" + context
        if key in _warned_dists:
            return
        _warned_dists.add(key)
        import warnings

        warnings.warn(
            f"[metadata-patch] Skipping corrupted distribution at {dist!r} ({context}): Input/output error — NTFS/fuse corruption. "
            f"Recreate venv on ext4 or run `ntfsfix`/`chkdsk`. App continues without that plugin.",
            RuntimeWarning,
            stacklevel=3,
        )
    except Exception:
        pass


# Auto-install on import so `import dataforge.core._metadata_patch` is enough
_install()

__all__ = ["_install"]
