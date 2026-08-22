"""Tests for TICK-302 — Service lifecycle files.

Validates:
- systemd user socket + service (Linux)
- D-Bus session service file (Linux)
- pywin32 ServiceFramework (Windows)
- SCM installer (Windows)
- launchd LaunchAgent plist (macOS)
- Engine entrypoint (__main__.py)

See: docs/PARALLEL_BACKLOG.md TICK-302
See: docs/proposals/NATIVE_OS_API_REVIEW.md §3.2
"""

from __future__ import annotations

import importlib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Paths to service lifecycle files
_SERVICE_DIR = Path(__file__).resolve().parent.parent / "dataforge" / "service"
_LINUX_DIR = _SERVICE_DIR / "linux"
_WINDOWS_DIR = _SERVICE_DIR / "windows"
_MACOS_DIR = _SERVICE_DIR / "macos"


# ---------------------------------------------------------------------------
# Linux — systemd user socket
# ---------------------------------------------------------------------------


class TestSystemdSocket:
    """Tests for dataforge/service/linux/dataforge.socket."""

    def test_socket_file_exists(self):
        """GIVEN the repo WHEN checking for dataforge.socket THEN it exists."""
        assert (_LINUX_DIR / "dataforge.socket").is_file()

    def test_socket_has_listen_stream(self):
        """GIVEN dataforge.socket WHEN parsed THEN ListenStream is %t/dataforge/engine.sock."""
        content = (_LINUX_DIR / "dataforge.socket").read_text()
        assert "ListenStream=%t/dataforge/engine.sock" in content

    def test_socket_mode_0700(self):
        """GIVEN dataforge.socket WHEN parsed THEN SocketMode is 0700."""
        content = (_LINUX_DIR / "dataforge.socket").read_text()
        assert "SocketMode=0700" in content

    def test_socket_has_install_section(self):
        """GIVEN dataforge.socket WHEN parsed THEN [Install] WantedBy=sockets.target."""
        content = (_LINUX_DIR / "dataforge.socket").read_text()
        assert "WantedBy=sockets.target" in content

    def test_socket_has_socket_section(self):
        """GIVEN dataforge.socket WHEN parsed THEN [Socket] section exists."""
        content = (_LINUX_DIR / "dataforge.socket").read_text()
        assert "[Socket]" in content


# ---------------------------------------------------------------------------
# Linux — systemd user service
# ---------------------------------------------------------------------------


class TestSystemdService:
    """Tests for dataforge/service/linux/dataforge.service."""

    def test_service_file_exists(self):
        """GIVEN the repo WHEN checking for dataforge.service THEN it exists."""
        assert (_LINUX_DIR / "dataforge.service").is_file()

    def test_service_exec_start(self):
        """GIVEN dataforge.service WHEN parsed THEN ExecStart uses dataforge-engine."""
        content = (_LINUX_DIR / "dataforge.service").read_text()
        assert "ExecStart=" in content
        assert "dataforge-engine" in content

    def test_service_restart_on_failure(self):
        """GIVEN dataforge.service WHEN parsed THEN Restart=on-failure."""
        content = (_LINUX_DIR / "dataforge.service").read_text()
        assert "Restart=on-failure" in content

    def test_service_requires_socket(self):
        """GIVEN dataforge.service WHEN parsed THEN Requires=dataforge.socket."""
        content = (_LINUX_DIR / "dataforge.service").read_text()
        assert "Requires=dataforge.socket" in content

    def test_service_type_simple(self):
        """GIVEN dataforge.service WHEN parsed THEN Type=simple."""
        content = (_LINUX_DIR / "dataforge.service").read_text()
        assert "Type=simple" in content

    def test_service_runtime_directory(self):
        """GIVEN dataforge.service WHEN parsed THEN RuntimeDirectory=dataforge."""
        content = (_LINUX_DIR / "dataforge.service").read_text()
        assert "RuntimeDirectory=dataforge" in content
        assert "RuntimeDirectoryMode=0700" in content


# ---------------------------------------------------------------------------
# Linux — D-Bus session service
# ---------------------------------------------------------------------------


class TestDBusService:
    """Tests for dataforge/service/linux/com.dataforge.Engine.service."""

    def test_dbus_file_exists(self):
        """GIVEN the repo WHEN checking for D-Bus service THEN it exists."""
        assert (_LINUX_DIR / "com.dataforge.Engine.service").is_file()

    def test_dbus_valid_xml(self):
        """GIVEN D-Bus service file WHEN parsed THEN it is valid XML."""
        tree = ET.parse(_LINUX_DIR / "com.dataforge.Engine.service")
        root = tree.getroot()
        assert root.tag == "busconfig"

    def test_dbus_service_name(self):
        """GIVEN D-Bus service file WHEN parsed THEN service name is com.dataforge.Engine."""
        tree = ET.parse(_LINUX_DIR / "com.dataforge.Engine.service")
        root = tree.getroot()
        service = root.find("service")
        assert service is not None
        assert service.get("name") == "com.dataforge.Engine"

    def test_dbus_executable(self):
        """GIVEN D-Bus service file WHEN parsed THEN executable is dataforge-engine."""
        tree = ET.parse(_LINUX_DIR / "com.dataforge.Engine.service")
        root = tree.getroot()
        service = root.find("service")
        assert service is not None
        executable = service.find("executable")
        assert executable is not None
        assert "dataforge-engine" in executable.text

    def test_dbus_type_session(self):
        """GIVEN D-Bus service file WHEN parsed THEN type is session."""
        tree = ET.parse(_LINUX_DIR / "com.dataforge.Engine.service")
        root = tree.getroot()
        bus_type = root.find("type")
        assert bus_type is not None
        assert bus_type.text == "session"


# ---------------------------------------------------------------------------
# Windows — ServiceFramework
# ---------------------------------------------------------------------------


class TestWindowsService:
    """Tests for dataforge/service/windows/service.py."""

    def test_service_module_importable(self):
        """GIVEN service.py WHEN imported THEN it loads without error."""
        mod = importlib.import_module("dataforge.service.windows.service")
        assert hasattr(mod, "DataForgeService")

    def test_service_class_attributes(self):
        """GIVEN DataForgeService WHEN inspected THEN has correct SCM attributes."""
        from dataforge.service.windows.service import DataForgeService

        assert DataForgeService._svc_name_ == "DataForgeEngine"
        assert DataForgeService._svc_display_name_ == "DataForge Engine"
        assert "Named Pipe" in DataForgeService._svc_description_

    def test_pipe_sddl_format(self):
        """GIVEN service.py WHEN imported THEN _PIPE_SDDL has correct DACL."""
        from dataforge.service.windows.service import _PIPE_SDDL

        # Must grant System (SY) and Administrators (BA) full access
        assert "GA;;;SY" in _PIPE_SDDL
        assert "GA;;;BA" in _PIPE_SDDL
        # Must grant Authenticated Users (AU) read/write
        assert "GRGW;;;AU" in _PIPE_SDDL

    def test_pipe_name(self):
        """GIVEN service.py WHEN imported THEN _PIPE_NAME is correct."""
        from dataforge.service.windows.service import _PIPE_NAME

        assert _PIPE_NAME == r"\\.\pipe\dataforge-engine"


# ---------------------------------------------------------------------------
# Windows — SCM installer
# ---------------------------------------------------------------------------


class TestWindowsInstall:
    """Tests for dataforge/service/windows/install.py."""

    def test_install_module_importable(self):
        """GIVEN install.py WHEN imported THEN it loads without error."""
        mod = importlib.import_module("dataforge.service.windows.install")
        assert hasattr(mod, "main")

    def test_install_has_all_commands(self):
        """GIVEN install.py WHEN imported THEN all command functions exist."""
        from dataforge.service.windows import install

        assert callable(install.install_service)
        assert callable(install.remove_service)
        assert callable(install.start_service)
        assert callable(install.stop_service)
        assert callable(install.status_service)

    def test_install_parser_has_subcommands(self):
        """GIVEN install.py WHEN building parser THEN all subcommands registered."""
        from dataforge.service.windows.install import _build_parser

        parser = _build_parser()
        # Verify the parser can parse each command
        for cmd in ("install", "remove", "start", "stop", "status"):
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_install_main_returns_int(self):
        """GIVEN install.py WHEN calling main with --help THEN it raises SystemExit."""
        from dataforge.service.windows.install import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# macOS — launchd plist
# ---------------------------------------------------------------------------


class TestMacOSPlist:
    """Tests for dataforge/service/macos/com.dataforge.engine.plist."""

    def test_plist_file_exists(self):
        """GIVEN the repo WHEN checking for plist THEN it exists."""
        assert (_MACOS_DIR / "com.dataforge.engine.plist").is_file()

    def test_plist_valid_xml(self):
        """GIVEN plist WHEN parsed THEN it is valid XML."""
        tree = ET.parse(_MACOS_DIR / "com.dataforge.engine.plist")
        root = tree.getroot()
        assert root.tag == "plist"

    def test_plist_label(self):
        """GIVEN plist WHEN parsed THEN Label is com.dataforge.engine."""
        tree = ET.parse(_MACOS_DIR / "com.dataforge.engine.plist")
        root = tree.getroot()
        # Find the <key>Label</key> followed by <string>com.dataforge.engine</string>
        dict_elem = root.find("dict")
        assert dict_elem is not None
        keys = dict_elem.findall("key")
        strings = dict_elem.findall("string")
        # Find index of "Label" key
        label_idx = None
        for i, key in enumerate(keys):
            if key.text == "Label":
                label_idx = i
                break
        assert label_idx is not None
        assert strings[label_idx].text == "com.dataforge.engine"

    def _parse_plist_dict(dict_elem) -> dict:
        """Parse a plist dict element into a Python dict (simplified)."""
        result = {}
        children = list(dict_elem)
        i = 0
        while i < len(children):
            if children[i].tag == "key":
                key = children[i].text
                if i + 1 < len(children):
                    value_elem = children[i + 1]
                    if value_elem.tag == "string":
                        result[key] = value_elem.text
                    elif value_elem.tag == "array":
                        result[key] = [s.text for s in value_elem.findall("string")]
                    elif value_elem.tag == "dict":
                        result[key] = TestMacOSPlist._parse_plist_dict(value_elem)
                    elif value_elem.tag == "true":
                        result[key] = True
                    elif value_elem.tag == "false":
                        result[key] = False
                    elif value_elem.tag == "integer":
                        result[key] = int(value_elem.text)
                    else:
                        result[key] = value_elem
                    i += 2
                else:
                    i += 1
            else:
                i += 1
        return result

    def test_plist_program_arguments(self):
        """GIVEN plist WHEN parsed THEN ProgramArguments contains dataforge-engine."""
        tree = ET.parse(_MACOS_DIR / "com.dataforge.engine.plist")
        root = tree.getroot()
        dict_elem = root.find("dict")
        assert dict_elem is not None
        plist = TestMacOSPlist._parse_plist_dict(dict_elem)
        assert "ProgramArguments" in plist
        assert any("dataforge-engine" in arg for arg in plist["ProgramArguments"])

    def test_plist_sockets_section(self):
        """GIVEN plist WHEN parsed THEN Sockets section with EngineSocket exists."""
        tree = ET.parse(_MACOS_DIR / "com.dataforge.engine.plist")
        root = tree.getroot()
        dict_elem = root.find("dict")
        assert dict_elem is not None
        plist = TestMacOSPlist._parse_plist_dict(dict_elem)
        assert "Sockets" in plist
        assert "EngineSocket" in plist["Sockets"]

    def test_plist_sock_path_mode(self):
        """GIVEN plist WHEN parsed THEN SockPathMode is 448 (0700 octal)."""
        tree = ET.parse(_MACOS_DIR / "com.dataforge.engine.plist")
        root = tree.getroot()
        dict_elem = root.find("dict")
        assert dict_elem is not None
        # Find all integer elements
        integers = dict_elem.findall(".//integer")
        # 448 = 0o700
        assert any(i.text == "448" for i in integers)

    def test_plist_run_at_load_false(self):
        """GIVEN plist WHEN parsed THEN RunAtLoad is false (socket activation)."""
        tree = ET.parse(_MACOS_DIR / "com.dataforge.engine.plist")
        root = tree.getroot()
        dict_elem = root.find("dict")
        assert dict_elem is not None
        keys = dict_elem.findall("key")
        # Find RunAtLoad key and verify the next element is <false/>
        for i, key in enumerate(keys):
            if key.text == "RunAtLoad":
                # The sibling after this key should be <false/>
                # In plist XML, keys and values alternate in the dict children
                children = list(dict_elem)
                # Find the index of this key in the full children list
                for j, child in enumerate(children):
                    if child is key:
                        next_child = children[j + 1]
                        assert next_child.tag == "false"
                        return
        pytest.fail("RunAtLoad key not found")


# ---------------------------------------------------------------------------
# Engine entrypoint (__main__.py)
# ---------------------------------------------------------------------------


class TestEngineEntrypoint:
    """Tests for dataforge/service/__main__.py."""

    def test_main_module_importable(self):
        """GIVEN __main__.py WHEN imported THEN it loads without error."""
        mod = importlib.import_module("dataforge.service.__main__")
        assert hasattr(mod, "main")

    def test_main_function_callable(self):
        """GIVEN __main__.py WHEN calling main THEN it is callable."""
        from dataforge.service.__main__ import main

        assert callable(main)

    def test_main_help_exits_zero(self):
        """GIVEN __main__.py WHEN calling main --help THEN exits 0."""
        from dataforge.service.__main__ import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_health_check_exits_one_stub(self):
        """GIVEN __main__.py WHEN calling main --health THEN exits 1 (stub mode)."""
        from dataforge.service.__main__ import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--health"])
        assert exc_info.value.code == 1

    def test_parser_socket_arg(self):
        """GIVEN __main__.py WHEN parsing --socket THEN it is accepted."""
        from dataforge.service.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--socket", "/tmp/test.sock"])
        assert args.socket == "/tmp/test.sock"

    def test_parser_pipe_arg(self):
        """GIVEN __main__.py WHEN parsing --pipe THEN it is accepted."""
        from dataforge.service.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--pipe", r"\\.\pipe\test"])
        assert args.pipe == r"\\.\pipe\test"

    def test_parser_dbus_flag(self):
        """GIVEN __main__.py WHEN parsing --dbus THEN it is True."""
        from dataforge.service.__main__ import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["--dbus"])
        assert args.dbus is True
