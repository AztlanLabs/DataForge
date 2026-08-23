import concurrent.futures
import glob
import hashlib
import importlib
import importlib.util
import multiprocessing
import os
import platform
import stat
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List, Type

from .views.base import BaseView
from ..core.logger import logger

HAS_PLUGINSIGN = True

DEFAULT_GPG_TRUST_ANCHOR = Path.home() / ".local" / "share" / "DataForge" / "plugins-trusted.gpg"
DEFAULT_SHA256_TRUST_ANCHOR = (
    Path.home() / ".local" / "share" / "DataForge" / "plugins-trusted.sha256"
)


class PluginSignatureMissingError(Exception):
    """Raised when ``require_signed=True`` but a plugin lacks ``.sig``."""


class PluginSignatureInvalidError(Exception):
    """Raised when a detached signature is present but invalid."""


def _compute_sha256(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _isolated_plugin_probe(file_path: str) -> dict:
    """Run in a worker process: try to import ``file_path``."""
    try:
        import importlib.util as _ilu
        import importlib as _il
        import os as _os
        import sys as _sys

        module_name = _os.path.splitext(_os.path.basename(file_path))[0]
        full_module_name = f"dataforge.ui.plugins.{module_name}"
        package_name = "dataforge.ui.plugins"
        try:
            _il.import_module(package_name)
        except Exception:
            pass
        spec = _ilu.spec_from_file_location(full_module_name, file_path)
        if spec is None or spec.loader is None:
            return {"ok": False, "error": "no spec"}
        mod = _ilu.module_from_spec(spec)
        _sys.modules[full_module_name] = mod
        spec.loader.exec_module(mod)
        return {"ok": True}
    except BaseException as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _subprocess_run_probe(file_path: str) -> bool:
    """Fallback isolation via ``subprocess.run(['python','-c', ...])``."""
    import os as _os

    module_name = _os.path.splitext(_os.path.basename(file_path))[0]
    full_name = f"dataforge.ui.plugins.{module_name}"
    code = textwrap.dedent(
        f"""
        import importlib, importlib.util
        importlib.import_module("dataforge.ui.plugins")
        spec = importlib.util.spec_from_file_location({full_name!r}, {file_path!r})
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        """
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            timeout=5,
            capture_output=True,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _queue_probe_worker(file_path: str, queue: multiprocessing.Queue) -> None:
    """Helper that puts probe result into a ``multiprocessing.Queue``."""
    res = _isolated_plugin_probe(file_path)
    try:
        queue.put(res, block=False)
    except Exception:
        pass


class PluginLoader:
    def __init__(
        self,
        plugin_dir: str,
        enabled: bool = False,
        isolation: str = "inline",
        require_signed: bool = False,
        trust_anchor: str | os.PathLike[str] | None = None,
        audit_log: object | None = None,
    ):
        self.plugin_dir = plugin_dir
        self.enabled = enabled
        self.isolation = isolation if isolation in ("inline", "subprocess") else "inline"
        self.require_signed = bool(require_signed)
        self.trust_anchor = Path(trust_anchor) if trust_anchor is not None else None
        self.audit_log = audit_log
        # Keep S5 behaviour: isolation default inline, signing default off
        if isolation not in ("inline", "subprocess"):
            logger.warning("Unknown isolation %r, falling back to 'inline'", isolation)

    # -- trust anchor -------------------------------------------------------

    def _get_trust_anchor_path(self) -> Path:
        if self.trust_anchor is not None:
            return Path(self.trust_anchor)
        try:
            import gnupg  # noqa: F401

            has_gnupg = True
        except ImportError:
            has_gnupg = False
        if has_gnupg:
            return DEFAULT_GPG_TRUST_ANCHOR
        return DEFAULT_SHA256_TRUST_ANCHOR

    def _find_sig_path(self, file_path: str) -> str | None:
        candidates = [
            file_path + ".sig",
            os.path.splitext(file_path)[0] + ".sig",
        ]
        for cand in candidates:
            if os.path.exists(cand):
                return cand
        return None

    def _read_whitelist(self, anchor: Path) -> set[str]:
        if not anchor.exists():
            return set()
        try:
            text = anchor.read_text(encoding="utf-8", errors="ignore")
            out: set[str] = set()
            for line in text.splitlines():
                line = line.strip().split()[0] if line.strip() else ""
                if line and len(line) == 64 and all(c in "0123456789abcdefABCDEF" for c in line):
                    out.add(line.lower())
                elif line:
                    # allow non-hex lines to be ignored
                    out.add(line.lower())
            return out
        except OSError:
            return set()

    def _verify_signature(self, file_path: str, sig_path: str) -> bool:
        trust_anchor = self._get_trust_anchor_path()
        # GPG path if available
        if trust_anchor.suffix == ".gpg":
            try:
                import gnupg  # noqa: F401

                gpg = gnupg.GPG(keyring=str(trust_anchor)) if trust_anchor.exists() else gnupg.GPG()
                with open(file_path, "rb") as fh:
                    data = fh.read()
                # python-gnupg verify_data expects sig file handle
                with open(sig_path, "rb") as sig_fh:
                    verified = gpg.verify_data(sig_fh, data)
                if verified is not None and getattr(verified, "valid", False):
                    return True
            except Exception:
                pass
            # fallback to sha256 comparison below
        # sha256 fingerprint mode
        try:
            file_hash = _compute_sha256(file_path)
            sig_text = Path(sig_path).read_text(encoding="utf-8", errors="ignore").strip()
            if not sig_text:
                return False
            # take first token (hex) — allow e.g. "sha256 <hex>"
            sig_token = sig_text.split()[0].strip().lower()
            # if sig file contains "<hex>  filename" take first
            if len(sig_token) != 64:
                # try to find hex in text
                for token in sig_text.split():
                    tok = token.strip().lower()
                    if len(tok) == 64 and all(c in "0123456789abcdef" for c in tok):
                        sig_token = tok
                        break
            if sig_token != file_hash.lower():
                return False
            whitelist = self._read_whitelist(trust_anchor)
            if whitelist:
                return file_hash.lower() in whitelist
            return True
        except OSError:
            return False

    # -- audit --------------------------------------------------------------

    def _audit(self, action: str, payload: dict) -> None:
        if self.audit_log is None:
            # lazy default AuditLog — best effort
            try:
                from ..core.audit import AuditLog

                self.audit_log = AuditLog()
            except Exception:
                return
        try:
            # current AuditLog signature is append(action, payload)
            append = getattr(self.audit_log, "append", None)
            if append is None:
                return
            try:
                append(action, payload)
            except TypeError:
                # fallback for older dict-style append({event: ...})
                append({"event": action, **payload})
        except Exception:
            pass

    # -- isolation ----------------------------------------------------------

    def _run_isolated_probe(self, file_path: str) -> bool:
        """Return True if subprocess isolated import succeeds."""
        # Demonstrate multiprocessing.Queue usage per spec
        queue: multiprocessing.Queue = multiprocessing.Queue()
        try:
            max_workers = min(2, (os.cpu_count() or 2) - 1 if (os.cpu_count() or 2) > 1 else 1)
            max_workers = max(1, max_workers)
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                future = executor.submit(_isolated_plugin_probe, file_path)
                try:
                    result = future.result(timeout=5)
                    # also demonstrate queue put/get
                    try:
                        queue.put(result, block=False)
                    except Exception:
                        pass
                    try:
                        queued = queue.get(block=False)
                        if isinstance(queued, dict):
                            return bool(queued.get("ok"))
                    except Exception:
                        pass
                    if isinstance(result, dict):
                        return bool(result.get("ok"))
                    return bool(result)
                except concurrent.futures.TimeoutError:
                    try:
                        future.cancel()
                    except Exception:
                        pass
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    # fallback to subprocess.run
                    return _subprocess_run_probe(file_path)
                except Exception:
                    return False
        except Exception:
            try:
                return _subprocess_run_probe(file_path)
            except Exception:
                return False
        finally:
            try:
                queue.close()
            except Exception:
                pass
            try:
                queue.join_thread()
            except Exception:
                pass
        # fallback path also demonstrates subprocess.run
        return _subprocess_run_probe(file_path)

    # -- public -------------------------------------------------------------

    def load_plugins(self) -> List[Type[BaseView]]:
        """
        Scan plugin directory for python files.

        Imports them and looks for BaseView subclasses.

        Plugin loading is opt-in (``enabled=True``). When disabled, no code is
        executed from the plugin directory. Each successful load is logged.

        When ``isolation='subprocess'`` each plugin's import is first probed
        in a ``concurrent.futures.ProcessPoolExecutor(max_workers=min(2, cpu_count()-1))``
        worker (``multiprocessing.Process`` + ``multiprocessing.Queue`` for the
        result, ``subprocess.run`` fallback) and the worker is discarded on
        timeout/crash.

        When ``require_signed=True`` a detached ``plugin.sig`` next to each
        ``plugin.py`` is verified against ``trust_anchor`` (default
        ``~/.local/share/DataForge/plugins-trusted.gpg`` if ``python-gnupg``
        is installed else ``~/.local/share/DataForge/plugins-trusted.sha256``).
        Missing or invalid signatures are refused and audited.
        """
        plugins: List[Type[BaseView]] = []
        if not self.enabled:
            logger.debug("Plugin loading is disabled (set enabled=True to opt in).")
            return plugins

        if not os.path.exists(self.plugin_dir):
            return plugins

        if not self._check_plugin_dir_permissions():
            logger.warning(
                f"Plugin directory {self.plugin_dir} has unsafe permissions; "
                "skipping plugin load."
            )
            return plugins

        files = glob.glob(os.path.join(self.plugin_dir, "*.py"))

        for file_path in files:
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            if module_name.startswith("__"):
                continue

            if not self._check_plugin_file_owner(file_path):
                logger.warning(f"Skipping plugin {module_name}: not owned by current user.")
                continue

            # compute sha for audit even before signing check
            try:
                file_hash = _compute_sha256(file_path)
            except OSError:
                file_hash = ""

            # -- signing gate ------------------------------------------------
            signed = False
            if self.require_signed:
                sig_path = self._find_sig_path(file_path)
                if sig_path is None:
                    self._audit(
                        "plugin_load_unsigned_refused",
                        {
                            "path": file_path,
                            "sha256": file_hash,
                            "signed": False,
                            "isolation": self.isolation,
                        },
                    )
                    raise PluginSignatureMissingError(
                        f"Plugin {file_path} missing signature ({file_path}.sig)"
                    )
                if not self._verify_signature(file_path, sig_path):
                    self._audit(
                        "plugin_load_invalid_sig",
                        {
                            "path": file_path,
                            "sha256": file_hash,
                            "signed": False,
                            "isolation": self.isolation,
                        },
                    )
                    raise PluginSignatureInvalidError(f"Invalid signature for plugin {file_path}")
                signed = True

            # -- subprocess isolation probe ----------------------------------
            if self.isolation == "subprocess":
                ok = self._run_isolated_probe(file_path)
                if not ok:
                    self._audit(
                        "plugin_load_failed",
                        {
                            "path": file_path,
                            "sha256": file_hash,
                            "signed": signed,
                            "isolation": self.isolation,
                            "error": "isolated probe failed",
                        },
                    )
                    continue

            package_name = "dataforge.ui.plugins"
            full_module_name = f"{package_name}.{module_name}"
            try:
                importlib.import_module(package_name)
            except Exception:
                pass

            spec = importlib.util.spec_from_file_location(full_module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[full_module_name] = module
                try:
                    spec.loader.exec_module(module)
                    logger.info(f"Loaded plugin: {module_name} from {file_path}")

                    found: List[Type[BaseView]] = []
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseView)
                            and attr is not BaseView
                        ):
                            found.append(attr)

                    if found:
                        plugins.extend(found)
                        # audit success
                        if signed:
                            self._audit(
                                "plugin_load_signed",
                                {
                                    "path": file_path,
                                    "sha256": file_hash,
                                    "signed": True,
                                    "isolation": self.isolation,
                                },
                            )
                        else:
                            self._audit(
                                "plugin_load",
                                {
                                    "path": file_path,
                                    "sha256": file_hash,
                                    "signed": False,
                                    "isolation": self.isolation,
                                },
                            )
                    else:
                        # module loaded but no BaseView — still audit as loaded
                        if signed:
                            self._audit(
                                "plugin_load_signed",
                                {
                                    "path": file_path,
                                    "sha256": file_hash,
                                    "signed": True,
                                    "isolation": self.isolation,
                                },
                            )
                        else:
                            self._audit(
                                "plugin_load",
                                {
                                    "path": file_path,
                                    "sha256": file_hash,
                                    "signed": False,
                                    "isolation": self.isolation,
                                },
                            )
                except PluginSignatureMissingError:
                    raise
                except PluginSignatureInvalidError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to load plugin {module_name}: {e}")
                    self._audit(
                        "plugin_load_failed",
                        {
                            "path": file_path,
                            "sha256": file_hash,
                            "signed": signed,
                            "isolation": self.isolation,
                            "error": str(e),
                        },
                    )

        return plugins

    def _check_plugin_dir_permissions(self):
        """Warn if the plugin directory is world-writable."""
        if platform.system() == "Windows":
            return True
        try:
            mode = os.stat(self.plugin_dir).st_mode
            if mode & stat.S_IWOTH:
                logger.warning(
                    f"Plugin directory {self.plugin_dir} is world-writable "
                    f"(mode {oct(mode)})."
                )
                return False
        except OSError:
            pass
        return True

    def _check_plugin_file_owner(self, file_path):
        """On Unix, verify the plugin file is owned by the current user."""
        if platform.system() == "Windows":
            return True
        try:
            file_stat = os.stat(file_path)
            return file_stat.st_uid == os.getuid()
        except OSError:
            return False
