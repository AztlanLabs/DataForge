# Native OS API Review — DataForge as a Real System Service

**Date:** 2026-08-22  
**Question:** "Create a native Linux/Windows/macOS API like a natural computer API does for internal calls/services."  
> **Status: PROPOSAL — not yet implemented.** This document describes future architecture against `dataforge/` HEAD at 2026-08-22. Current truth lives in `../APP_REFERENCE.md`, `../ARCHITECTURE.md`, and `../TECHNICAL_SOURCE_OF_TRUTH.md`. Do not treat paths, service files, or APIs here as shipped.

**Verdict on previous doc:** `PERFORMANCE_INVESTIGATION.md §3` was right to split app ↔ engine, but `FastAPI over HTTP` alone is **not native** — it feels like a web service, not a system service. This doc keeps the split, replaces HTTP-as-primary with **OS-native IPC + service lifecycle + native FS syscalls**, and keeps HTTP only as the *remote* gateway.

---

## 1. What the Previous Proposal Got Right / Wrong

| Previous (§3) | Keep? | Why |
|---|---|---|
| App ↔ Engine split, `FileProvider` ABC | **Keep** | Correct seam. `core/provider.py:4` is the right place, just empty today. |
| Job model: `jobs/{id}` + `progress_callback` + `cancel_token` | **Keep** | Maps 1:1 to any transport (SSE, D-Bus signal, XPC event). |
| Engine as importable lib (`dataforge/engine`) | **Keep** | Lets CLI/GUI run in-process for tests, out-of-process for prod. |
| **FastAPI + HTTP as primary IPC** | **Change** | HTTP on `127.0.0.1:8000` is *alien* on desktop: no OS service registry, no permission model, no socket activation, firewall prompts on Windows, no Keychain/polkit integration, extra TCP stack. Tools that feel native (Docker, VS Code, 1Password, Spotlight, Windows Search) use **UDS / Named Pipes / D-Bus / XPC** locally and expose HTTP only for *remote*. |
| Single `BackgroundWorker(QThread)` | **Replace** | Covered in previous doc — becomes engine-side queue. |

**Goal for "native":** Installing DataForge should feel like installing Docker Desktop or Dropbox:
- `systemctl status dataforge` / `sc query dataforge` / `launchctl list | grep dataforge` works.
- GUI/CLI talk to the engine without knowing host/port — they discover the socket/pipe/bus name.
- OS permission dialogs (polkit / UAC / TCC) appear where needed, not custom password prompts.
- File watching, trash, indexing use OS-native events, not polling.

---

## 2. What "Native OS API" Actually Means — 3 Layers

Most people hear "native API" and think "fast syscalls." For a forensic-grade tool it is 3 layers:

```
Layer 1 — Service Lifecycle   How the OS starts/stops/updates the engine
Layer 2 — IPC (the API)       How GUI/CLI/other apps call the engine
Layer 3 — Filesystem Native   How the engine talks to disk efficiently
```

All three must be native, or one layer leaks slowness/insecurity.

### Layer 1 — Service Lifecycle

| OS | Native mechanism | What DataForge should ship |
|---|---|---|
| **Linux** | `systemd` user service + socket activation | `~/.config/systemd/user/dataforge.service` + `dataforge.socket` (UDS at `$XDG_RUNTIME_DIR/dataforge/engine.sock`) |
| **Windows** | Windows Service (SCM) + auto-start | `dataforge-service.exe` registered via `sc create`, runs as `NT SERVICE\DataForge`, exposes `\\.\pipe\dataforge-engine` |
| **macOS** | `launchd` LaunchAgent + XPC | `~/Library/LaunchAgents/com.dataforge.engine.plist` → `~/Library/Application Support/DataForge/engine.sock` + XPC service for privileged ops |

Why not just `python -m dataforge.api &`? No lifecycle, no crash restart, no socket activation (service starts on first GUI open, not at login), no OS update integration.

### Layer 2 — IPC (the actual API)

| OS | Primary (local) | Secondary (discoverable) | Remote fallback |
|---|---|---|---|
| **Linux** | **Unix Domain Socket** (`SOCK_STREAM`, `0700`) at `$XDG_RUNTIME_DIR/dataforge/engine.sock` | **D-Bus** session bus `com.dataforge.Engine` (introspectable by `d-feet`, `busctl`) | HTTP gateway on `127.0.0.1` → `0.0.0.0` with token |
| **Windows** | **Named Pipe** `\\.\pipe\dataforge-engine` (ACL: current user + Administrators) | **COM** local server `DataForge.Engine` (optional, for PowerShell/Explorer) | Same HTTP gateway |
| **macOS** | **Unix Domain Socket** at `$HOME/Library/Application Support/DataForge/engine.sock` (0700) | **XPC** `com.dataforge.engine.xpc` for privileged helper (SMART, raw disk) | Same |

**Why not HTTP locally?** UDS/Named Pipes are:
- 30-50% lower latency (no TCP, no HTTP parsing, no port allocation).
- Filesystem-permissioned (`0700` socket, `SDDL` on pipe) — no token in URL, no `127.0.0.1` firewall popup on Windows.
- Socket-activated: `systemd`/`launchd` starts engine on first connect, not at boot.

**Why also D-Bus / XPC / COM?** So DataForge *looks like the OS*:
- `busctl call com.dataforge.Engine /com/dataforge/Engine com.dataforge.Engine Scan ...` works on Linux — scriptable without Python.
- Spotlight/Quick Look extensions on macOS can call XPC directly.
- PowerShell `New-Object -ComObject DataForge.Engine` works on Windows.

HTTP/gRPC stays for **remote** (SSH tunnel, headless server, CI). It is not removed — it becomes the *remote* transport, not the *local* one.

### Layer 3 — Filesystem Native

| Area | Python today (`os.scandir`, `hashlib`, `os.walk`) | Native fast path |
|---|---|---|
| **Scan** | `os.scandir` sequential, double `stat` (`core/scanner.py:6`) | Linux: `getdents64` via `os.scandir` + `io_uring` batch stat; fallback `scandir` parallel BFS. macOS: `getattrlistbulk` + `FSEvents` for incremental. Windows: `FindFirstFileW` / `NtQueryDirectoryFile` + `ReadDirectoryChangesW`. |
| **Hash** | `hashlib` 64 KiB loop, `ThreadPool(4)` | Rust `blake3`/`xxhash` via `PyO3`, `mmap`, `posix_fadvise(WILLNEED)` / `madvise`; Windows `CreateFile` `FILE_FLAG_SEQUENTIAL_SCAN` + overlapped I/O. |
| **Watch** | Polling (none) | Linux `inotify`/`fanotify`, macOS `FSEvents`/`EndpointSecurity`, Windows `USN Journal` + `ReadDirectoryChangesW`. |
| **Trash** | `send2trash` (shells out) | Linux: `gio trash` D-Bus `org.freedesktop.FileManager1`, Windows: `IFileOperation` COM, macOS: `NSFileManager trashItemAtURL`. |
| **Disk health** | `psutil`/`smartctl` subprocess | Linux: `libatasmart` via `udev`, Windows: `DeviceIoControl(IOCTL_STORAGE_QUERY_PROPERTY)`, macOS: `IOKit` `SMART`. |

This is where "ridiculously fast" actually lives — not just threads, but fewer syscalls.

---

## 3. Unified Design — One API, Three Transports

```
┌──────────────────────────────────────────────────────────┐
│  Client SDK (Python)  dataforge/client/__init__.py      │
│  engine = await DataForge.connect()  # auto-discovers   │
│  job = await engine.scan("/home/me", recursive=True)    │
│  async for event in job.events(): print(event.progress) │
└──────────────────┬───────────────────────────────────────┘
                   │  JSON-RPC 2.0 over framed MessagePack (or Cap'n Proto)
                   │  Same schema on every transport
      ┌────────────┼────────────┐
      ▼            ▼            ▼
   UDS (Linux/   Named Pipe   HTTP/gRPC
   macOS)       (Windows)    (remote)
      └────────────┼────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│  Engine Daemon  dataforge/engine/daemon.py              │
│  - JobQueue (asyncio + ThreadPool + ProcessPool for hash)│
│  - Transports: UdsTransport, NamedPipeTransport,         │
│                DbusTransport, XpcTransport, HttpGateway │
│  - Providers: LocalProvider (native FS), SshProvider,   │
│               S3Provider, ImageProvider (pytsk3)        │
└──────────────────────────────────────────────────────────┘
```

### 3.1 Protocol — Same on every transport

Pick **JSON-RPC 2.0 over length-prefixed MessagePack** (or `Cap'n Proto` if you add Rust). Why not plain HTTP JSON? Framing is transport-agnostic, binary is small, streaming is natural (`job.events` is a subscription, not polling).

```json
// Request (over UDS, Named Pipe, or HTTP POST)
{"jsonrpc":"2.0","id":1,"method":"scan","params":{
  "provider":"local", "root":"/home/crowne", "recursive":true, "max_depth":-1
}}
// Response
{"jsonrpc":"2.0","id":1,"result":{"job_id":"01J..."}}
// Event stream (length-prefixed frames, or D-Bus signal / XPC event)
{"job_id":"01J...","type":"progress","current":42000,"total":0,"message":"Scanning files..."}
{"job_id":"01J...","type":"result","payload":{"total":512000,"by_format":{"JPEG":1200}}}
```

The key is **transport is pluggable** — `DataForge.connect()` tries in order:
1. `$DATAFORGE_ENGINE_SOCK` env (explicit)
2. `$XDG_RUNTIME_DIR/dataforge/engine.sock` (Linux, `0700`, `systemd` socket-activated)
3. `~/Library/Application Support/DataForge/engine.sock` (macOS)
4. `\\.\pipe\dataforge-engine` (Windows, `win32pipe`)
5. `http://127.0.0.1:8765` (dev fallback, then `https://host:8765` for remote with token)

Client code never knows which it got.

### 3.2 Service — How it runs

**Linux:**
```ini
# ~/.config/systemd/user/dataforge.socket
[Socket]
ListenStream=%t/dataforge/engine.sock
SocketMode=0700
# ~/.config/systemd/user/dataforge.service
[Service]
ExecStart=%h/.local/bin/dataforge-engine --socket %t/dataforge/engine.sock --dbus
Restart=on-failure
```
D-Bus service file at `~/.local/share/dbus-1/services/com.dataforge.Engine.service` for `busctl` discovery. `polkit` rule for privileged ops (SMART, raw disk) — prompts via system dialog, not app dialog.

**Windows:**
```python
# dataforge/service/windows/service.py — pywin32
class DataForgeService(win32serviceutil.ServiceFramework):
    _svc_name_ = "DataForgeEngine"
    _svc_display_name_ = "DataForge Engine"
    def SvcDoRun(self):
        # Create Named Pipe \\.\pipe\dataforge-engine with SDDL:
        # D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU) — System, Admin, Authenticated Users
        # + HTTP gateway on 127.0.0.1:8765 (loopback only)
```

**macOS:**
```xml
<!-- ~/Library/LaunchAgents/com.dataforge.engine.plist -->
<key>ProgramArguments</key><array><string>/Applications/DataForge.app/Contents/MacOS/dataforge-engine</string></array>
<key>Sockets</key><dict><key>EngineSocket</key><dict><key>SockPathName</key><string>.../engine.sock</string></dict></dict>
```
Privileged helper via `SMJobBless` + XPC `com.dataforge.engine.privileged` for raw-disk/SMART — shows macOS auth dialog, stores in Keychain.

### 3.3 Filesystem Native — Concrete per-Provider

```python
# dataforge/core/provider.py — expanded
class FileProvider(ABC):
    def list_files(self, root: str, recursive=True) -> Iterable[FileEntry]: ...
    def list_files_parallel(self, root: str) -> Iterable[FileEntry]: ...
    def stat(self, path: str) -> os.stat_result: ...
    def open(self, path: str, mode="rb"): ...
    def hash(self, path: str, algo="sha256") -> str: ...
    def hash_many(self, paths: list[str], algo="sha256") -> dict[str,str]: ...

class LocalProvider(FileProvider):
    # Linux: parallel BFS with os.scandir + entry.stat(follow_symlinks=False), no build_file_entry double-stat
    # macOS: getattrlistbulk for bulk stat, FSEvents for incremental
    # Windows: FindFirstFileW + GetFileInformationByHandleEx, USN Journal for incremental
    # Hash: Rust blake3 via dataforge_native.pyd/so, mmap + posix_fadvise / FILE_FLAG_SEQUENTIAL_SCAN
```

Add `dataforge_native` Rust crate (PyO3) exposing `hash_file(path, algo)`, `scan_dir_parallel(root)`, `watch_dir(root, callback)` — Python falls back to pure-Python when crate not compiled, so dev stays simple, prod is fast.

---

## 4. Security — Native Means OS-Managed

| Concern | UDS (Linux/macOS) | Named Pipe (Windows) | D-Bus / XPC |
|---|---|---|---|
| Who can connect? | `0700` socket, `SO_PEERCRED` → check `uid` | SDDL `D:(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;AU)`, `GetNamedPipeClientProcessId` | D-Bus `GetConnectionUnixUser`, XPC `xpc_connection_get_euid` |
| Forensic chain (`F1`) | Job DB at `~/.dataforge/jobs.db` `0600`, WAL, hash-chained entries (see `FORENSIC_REVIEW.md:F1`) | Same, plus DPAPI-encrypted job DB | Same, Keychain for token |
| Privileged ops | `polkit` (`org.dataforge.engine.privileged`) | UAC `runas` helper | `SMJobBless` XPC helper |
| Remote | mTLS + token in `~/.dataforge/engine.token` `0600`, not URL | Same | Same |

Do not invent auth — use the OS. Local UDS/Named Pipe is *already* auth via filesystem ACL.

---

## 5. What to Ship — File Map

```
dataforge/
  engine/
    daemon.py              # main loop, JobQueue
    jobs.py                # Job {id, provider, params, progress, cancel_token, results}
    index.py               # SQLite FTS5 / Tantivy index for sub-second search
  api/
    schema.py              # Pydantic ScanRequest/SearchRequest/... (shared with HTTP)
    transport/
      base.py              # Transport ABC: send(), recv(), subscribe()
      uds.py               # Unix Domain Socket (Linux, macOS) — asyncio.start_unix_server
      named_pipe.py        # Windows Named Pipe — win32pipe / asyncio Proactor
      dbus.py              # D-Bus session bus — dbus-next, introspectable
      xpc.py               # macOS XPC shim (UDS + launchd Mach service)
      http_gateway.py      # FastAPI app for remote, reuses schema.py
  service/
    __main__.py            # dataforge-engine entrypoint
    linux/
      dataforge.socket
      dataforge.service
      com.dataforge.Engine.service
    windows/
      service.py
      install.py
    macos/
      com.dataforge.engine.plist
      privileged_helper.py
  client/
    __init__.py            # DataForge.connect() auto-discovers transport
    sync.py / async.py     # Sync wrapper for CLI, async for GUI
  core/
    provider.py            # Expanded ABC (see §3.3)
    scanner.py             # Now calls provider.list_files_parallel
    hasher.py              # Calls dataforge_native if present, else hashlib
  native/                  # Rust crate (optional, not required for dev)
    Cargo.toml
    src/lib.rs             # blake3, scan, watch via PyO3
```

GUI (`ui/app.py`) change is minimal:
```python
# Before: self.current_worker = BackgroundWorker(target, ...)
# After:
from dataforge.client import DataForge
self.engine = await DataForge.connect()  # discovers UDS/pipe/HTTP
job = await self.engine.scan(path)
job.events.connect(self.update_progress)  # same progress_callback shape
# Falls back to in-process engine if daemon not running (dev mode): DataForge.connect(in_process=True)
```

CLI (`dataforge/cli.py`) same — `fm search ...` calls `DataForge.connect()` then `engine.search(..., stream=True)` and prints JSONL.

---

## 6. Decision — Recommendation

**Use hybrid, not pure HTTP:**

- **Primary local:** UDS (Linux/macOS) + Named Pipes (Windows) with length-prefixed MessagePack JSON-RPC. This is the *native* path — fastest, permissioned, socket-activated, no port.
- **Secondary discoverable:** D-Bus (Linux) + XPC (macOS) + COM (Windows) wrappers that proxy to the same engine — so the OS *sees* DataForge as a system service.
- **Remote:** HTTP/gRPC gateway (FastAPI) that reuses the same `api/schema.py` — for headless, SSH tunnel, CI.

**Why this over pure HTTP/gRPC?** HTTP is great for remote, but locally it is the *least* native option: it needs a port, triggers Windows Firewall, has no filesystem ACL, and isn’t socket-activated. UDS/Named Pipes *are* the native desktop IPC on each OS — Docker, VS Code Server, 1Password, and Windows Search all do it this way and add HTTP only for remote.

If you must pick one transport to start: **UDS + Named Pipes** (single codebase, `asyncio` on POSIX + `ProactorEventLoop` on Windows) gives you native on all three OSes in one PR. Add D-Bus/XPC/COM in the next PR for discoverability.

---

## 7. Roadmap — Native-First, No Rewrite (now with install/upgrade)

> **Addendum 2026-08-22 — Installable/Removable/Upgradable.** Service lifecycle (N1) now depends on packaging. See [`INSTALL_UPGRADE_LIFECYCLE.md`](./INSTALL_UPGRADE_LIFECYCLE.md) for full file layout, versioning, migration, and per-OS installer spec. Phase I0 below must land *before* N1.

| Phase | Ships | Effort | Unlocks |
|---|---|---|---|
| **I0. Paths + version + migrations** | `core/paths.py` (platformdirs), `CONFIG_SCHEMA_VERSION`, `PRAGMA user_version`, `__version__`, legacy `~/.dataforge` migration | S (3-4 days) | Installable without data loss — unblocks packaging |
| **N0. Engine lib + UDS/Named Pipe transport** | `engine/daemon.py`, `api/transport/{uds,named_pipe,base}.py`, `client/__init__.py` auto-discover, `provider.py` expanded, `scanner.py` parallel BFS | S (1-1.5 wks) | GUI/CLI talk to out-of-process engine locally, 3-5× scan, no HTTP needed |
| **I1. Onedir bundle + deb/rpm** | `build_exe.py` onedir, `packaging/nfpm.yaml`, `postinst`/`prerm` systemd units, `.desktop` | S (1 wk) | `apt install ./dataforge.deb` → `systemctl --user status dataforge` works |
| **N1. Service lifecycle** | `service/linux+windows+macos` units, socket activation, `dataforge-engine` binary entry | S (1 wk) | `systemctl`/`sc`/`launchctl` works, engine starts on demand |
| **I2 + N2. Windows msi + macOS dmg/pkg + HTTP gateway** | WiX `Product.wxs`, `launchd` plist, `brew cask`, `api/transport/http_gateway.py` | M (1.5 wks) | `winget`/`brew`, Add/Remove, remote `fm --engine https://host` |
| **N3. D-Bus / XPC / COM** | `api/transport/{dbus,xpc}` proxies | M (1 wk) | `busctl`, Spotlight, PowerShell discover DataForge |
| **N4. Native FS + Rust helper + auto-update** | `native/` crate, `hasher.py` mmap+blake3, `inotify`/`FSEvents`/`USN` watch, `index.py` FTS, Sparkle/`winget` updater | L (2-3 wks) | Ridiculous speed, incremental search, <10s 1M-file scan |

Order is I0 → N0 → I1 → N1 → (I2+N2) → N3 → N4. I0 is 3-4 days and must come first — without `paths.py` + migrations, packaging orphans `~/.dataforge` and upgrades lose settings. Previous doc’s P0 (parallel walk, batched cache, 1 MiB blocks) lands *inside* N0.

---

## 8. What to Do Today

1. **Approve transport:** Confirm UDS+Named Pipes as primary local (vs. gRPC-UDS). If you prefer gRPC, swap MessagePack for `grpc` with `unix://` scheme — same sockets, different framing.
2. **I scaffold N0** on a branch: `engine/daemon.py` + `api/transport/uds.py+named_pipe.py` + `client/DataForge.connect()` + `provider.py` v2, with `scanner.py` calling `provider.list_files_parallel`. GUI keeps working via `in_process` fallback, so no flag day.
3. **You pick one OS for first service file** (Linux `systemd` is fastest to test) — I ship the `.socket`/`.service` and we validate `DataForge.connect()` auto-discovers it.

Want me to start N0 (UDS/Named Pipe engine + auto-discovering client) or draft the `dataforge_native` Rust crate interface first?
