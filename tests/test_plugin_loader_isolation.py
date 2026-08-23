import hashlib
import sys
from pathlib import Path

import pytest

from dataforge.core.audit import AuditLog
from dataforge.ui.plugin_loader import (
    PluginLoader,
    PluginSignatureInvalidError,
    PluginSignatureMissingError,
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_plugin(path: Path, name: str = "TestPlugin") -> None:
    path.write_text(
        f"""
from dataforge.ui.views.base import BaseView

class {name}(BaseView):
    def get_title(self):
        return "{name}"
""",
        encoding="utf-8",
    )


def _cleanup_modules(prefix: str = "dataforge.ui.plugins"):
    for mod in list(sys.modules.keys()):
        if mod.startswith(prefix):
            # keep the package itself
            if mod == "dataforge.ui.plugins":
                continue
            # only remove test modules we created
            if "test_" in mod or "malicious" in mod or "signed" in mod or "unsigned" in mod:
                sys.modules.pop(mod, None)


def test_subprocess_isolation_malicious_plugin(tmp_path):
    """AC1: isolation='subprocess' malicious plugin does not propagate."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    # malicious plugin raises at import
    malicious = plugin_dir / "malicious_plugin.py"
    malicious.write_text("raise ZeroDivisionError('boom')\n", encoding="utf-8")
    audit_db = tmp_path / "audit.db"
    audit = AuditLog(db_path=str(audit_db))

    loader = PluginLoader(
        str(plugin_dir), enabled=True, isolation="subprocess", audit_log=audit
    )
    # should not raise, should return []
    result = loader.load_plugins()
    assert result == []

    # audit entry plugin_load_failed appended
    entries = audit.get_entries(limit=10)
    actions = [e["action"] for e in entries]
    assert "plugin_load_failed" in actions
    # find payload for malicious
    for e in entries:
        if e["action"] == "plugin_load_failed":
            payload = e["payload"]
            assert "malicious" in payload.get("path", "")
            assert payload.get("isolation") == "subprocess"
            break
    else:
        pytest.fail("plugin_load_failed not found")
    _cleanup_modules()
    audit.close()


def test_require_signed_valid_sig_loads(tmp_path):
    """AC2: require_signed=True with valid sig loads and audits signed."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "signed_plugin.py"
    _write_plugin(plugin_file, name="SignedPlugin")

    file_hash = _sha256(plugin_file)
    sig_path = Path(str(plugin_file) + ".sig")
    sig_path.write_text(file_hash, encoding="utf-8")

    whitelist = tmp_path / "whitelist.sha256"
    whitelist.write_text(file_hash + "\n", encoding="utf-8")

    audit_db = tmp_path / "audit.db"
    audit = AuditLog(db_path=str(audit_db))

    loader = PluginLoader(
        str(plugin_dir),
        enabled=True,
        require_signed=True,
        trust_anchor=str(whitelist),
        audit_log=audit,
    )
    result = loader.load_plugins()
    names = {cls.__name__ for cls in result}
    assert "SignedPlugin" in names

    entries = audit.get_entries(limit=10)
    actions = [e["action"] for e in entries]
    assert "plugin_load_signed" in actions
    for e in entries:
        if e["action"] == "plugin_load_signed":
            assert e["payload"]["sha256"] == file_hash
            assert e["payload"]["signed"] is True
            break
    _cleanup_modules()
    audit.close()


def test_require_signed_missing_sig_raises(tmp_path):
    """AC3: require_signed=True without .sig raises and audits refused."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "unsigned_plugin.py"
    _write_plugin(plugin_file, name="UnsignedPlugin")

    whitelist = tmp_path / "whitelist.sha256"
    whitelist.write_text("abc\n", encoding="utf-8")

    audit_db = tmp_path / "audit.db"
    audit = AuditLog(db_path=str(audit_db))

    loader = PluginLoader(
        str(plugin_dir),
        enabled=True,
        require_signed=True,
        trust_anchor=str(whitelist),
        audit_log=audit,
    )
    with pytest.raises(PluginSignatureMissingError):
        loader.load_plugins()

    entries = audit.get_entries(limit=10)
    assert any(e["action"] == "plugin_load_unsigned_refused" for e in entries)
    _cleanup_modules()
    audit.close()


def test_require_signed_invalid_sig_raises(tmp_path):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "bad_plugin.py"
    _write_plugin(plugin_file, name="BadPlugin")
    sig_path = Path(str(plugin_file) + ".sig")
    sig_path.write_text("0" * 64, encoding="utf-8")  # wrong hash

    whitelist = tmp_path / "whitelist.sha256"
    whitelist.write_text("0" * 64 + "\n", encoding="utf-8")

    audit = AuditLog(db_path=str(tmp_path / "audit.db"))
    loader = PluginLoader(
        str(plugin_dir),
        enabled=True,
        require_signed=True,
        trust_anchor=str(whitelist),
        audit_log=audit,
    )
    with pytest.raises(PluginSignatureInvalidError):
        loader.load_plugins()
    entries = audit.get_entries(limit=10)
    assert any(e["action"] == "plugin_load_invalid_sig" for e in entries)
    _cleanup_modules()
    audit.close()


def test_require_signed_false_backwards_compat(tmp_path):
    """AC4: require_signed=False (default) preserves opt-in + S5 checks."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "compat_plugin.py"
    _write_plugin(plugin_file, name="CompatPlugin")

    audit = AuditLog(db_path=str(tmp_path / "audit.db"))
    # default require_signed=False, isolation inline
    loader = PluginLoader(str(plugin_dir), enabled=True, audit_log=audit)
    result = loader.load_plugins()
    assert any(cls.__name__ == "CompatPlugin" for cls in result)

    # also verify opt-in still works: disabled should load nothing
    loader2 = PluginLoader(str(plugin_dir), enabled=False, audit_log=audit)
    assert loader2.load_plugins() == []

    # world-writable dir should be rejected (S5 preserved) when isolation inline
    # chmod 777
    plugin_dir.chmod(0o777)
    try:
        loader3 = PluginLoader(str(plugin_dir), enabled=True, audit_log=audit)
        assert loader3.load_plugins() == []
    finally:
        plugin_dir.chmod(0o755)
    _cleanup_modules()
    audit.close()


def test_inline_returns_same_as_before(tmp_path):
    """AC5: isolation='inline' loads MetadataCleanerPlugin like before."""
    repo_root = Path(__file__).resolve().parents[1]
    plugin_dir = repo_root / "dataforge" / "ui" / "plugins"

    audit = AuditLog(db_path=str(tmp_path / "audit.db"))
    loader = PluginLoader(str(plugin_dir), enabled=True, isolation="inline", audit_log=audit)
    result = loader.load_plugins()
    names = {cls.__name__ for cls in result}
    assert "MetadataCleanerPlugin" in names

    # also check subprocess isolation returns same for existing plugin
    audit2 = AuditLog(db_path=str(tmp_path / "audit2.db"))
    loader_sub = PluginLoader(
        str(plugin_dir), enabled=True, isolation="subprocess", audit_log=audit2
    )
    result2 = loader_sub.load_plugins()
    names2 = {cls.__name__ for cls in result2}
    assert "MetadataCleanerPlugin" in names2
    _cleanup_modules()
    audit.close()
    audit2.close()


def test_audit_appends_for_each_load(tmp_path):
    """Each successful load appends AuditLog entry with sha256/signed/isolation."""
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    for i in range(2):
        _write_plugin(plugin_dir / f"plug{i}.py", name=f"Plug{i}")

    audit = AuditLog(db_path=str(tmp_path / "audit.db"))
    loader = PluginLoader(str(plugin_dir), enabled=True, isolation="inline", audit_log=audit)
    result = loader.load_plugins()
    assert len(result) == 2
    entries = audit.get_entries(limit=10)
    loads = [e for e in entries if e["action"] in ("plugin_load", "plugin_load_signed")]
    assert len(loads) == 2
    for e in loads:
        assert "sha256" in e["payload"]
        assert "signed" in e["payload"]
        assert e["payload"]["isolation"] == "inline"
    _cleanup_modules()
    audit.close()
