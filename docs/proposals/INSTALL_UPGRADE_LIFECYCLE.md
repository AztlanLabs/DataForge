# Install / Remove / Upgrade Lifecycle — DataForge as a Native Package

**Date:** 2026-08-22  
**Companion:** [`NATIVE_OS_API_REVIEW.md`](./NATIVE_OS_API_REVIEW.md) (service + IPC), [`PERFORMANCE_INVESTIGATION.md`](./PERFORMANCE_INVESTIGATION.md) (engine)  
> **Status: PROPOSAL — not yet implemented.** This document describes future architecture against `dataforge/` HEAD at 2026-08-22. Current truth lives in `../APP_REFERENCE.md`, `../ARCHITECTURE.md`, and `../TECHNICAL_SOURCE_OF_TRUTH.md`. Do not treat paths, service files, or APIs here as shipped.

**Goal:** Behave like a real OS package: installable in one command, cleanly removable, safely upgradable with migrations and zero user-data loss.

---

## 0. Current State — Why You Can't Ship Today

| Area | Today (`pyproject.toml:8`, `build_exe.py:46`, `core/config.py:48`, `core/cache.py:9`, `core/logger.py:40`) | Why it blocks install/upgrade |
|---|---|---|
| **Version** | `pyproject.toml:7` `version="0.1.0"` hardcoded, `dataforge/__init__.py` has no `__version__`, no `version.json` | No reliable way for installer/updater/service to know what is installed |
| **Data location** | Everything in `~/.dataforge/` (`config.json`, `cache.db`, `app.log`) on all OSes | Violates XDG on Linux, `AppData` on Windows, `Application Support` on macOS. Breaks roaming, backups, and per-OS uninstall expectations |
| **Config** | `ConfigManager:48` writes JSON directly, no schema version, `_merge_validated` drops unknown keys | Upgrading can’t migrate old keys; downgrading silently loses data |
| **Cache/DB** | `cache.py:20` single `file_hashes` table, no `PRAGMA user_version`, no migration table | Schema change (e.g., adding `st_ino` for hardlink dedup) requires destructive `DELETE`/`VACUUM` |
| **Service** | No `systemd`/`launchd`/Windows Service files. `run_ui.py` and `dataforge-engine` are just Python processes | `build_exe.py:46` produces a windowed onefile exe (`DataForge`) with no service registration, no desktop entry, no uninstall hook |
| **Installer** | `setup.py:7` shim + `pip install -e .` + `build_exe.py` (PyInstaller onefile) | No `.deb`/`.rpm`/`.msi`/`.pkg`/`.dmg`, no repo, no `Add/Remove Programs`, no `brew`, no atomic replace, no rollback |
| **Uninstall** | No `prerm`/`postrm`, no `UninstallString` | Files in `~/.dataforge` and service files would be orphaned |

**Rule for this doc:** Every new path, service, or schema gets a **versioned, migratable, removable** story from day one.

---

## 1. Canonical Layouts — Where Files Live (after this change)

Use `platformdirs` (tiny, no deps) and keep `~/.dataforge` as a **1-version migration source**, not the canonical location.

| Kind | Linux (XDG) | macOS | Windows | Var name |
|---|---|---|---|---|
| **Bin** | `~/.local/bin/dataforge`, `~/.local/bin/dataforge-engine` (pip) or `/usr/bin/dataforge` (deb/rpm) or `/opt/dataforge/DataForge` (onefile bundle) | `/Applications/DataForge.app/Contents/MacOS/DataForge` + `/usr/local/bin/dataforge` shim (pkg) or `~/Applications` (dmg) | `%ProgramFiles%\DataForge\DataForge.exe` + `dataforge-engine.exe` | `bin_dir` |
| **Config** | `$XDG_CONFIG_HOME/dataforge/config.json` → `~/.config/dataforge/config.json` | `~/Library/Application Support/DataForge/config.json` | `%AppData%\DataForge\config.json` | `config_dir` |
| **Cache** | `$XDG_CACHE_HOME/dataforge/cache.db` → `~/.cache/dataforge/cache.db` | `~/Library/Caches/DataForge/cache.db` | `%LocalAppData%\DataForge\Cache\cache.db` | `cache_dir` |
| **State (jobs, index)** | `$XDG_STATE_HOME/dataforge/jobs.db` → `~/.local/state/dataforge/jobs.db` | `~/Library/Application Support/DataForge/jobs.db` | `%LocalAppData%\DataForge\jobs.db` | `state_dir` |
| **Logs** | `$XDG_STATE_HOME/dataforge/logs/app.log` | `~/Library/Logs/DataForge/app.log` | `%LocalAppData%\DataForge\Logs\app.log` | `log_dir` |
| **Runtime (socket)** | `$XDG_RUNTIME_DIR/dataforge/engine.sock` (`/run/user/$UID/...`, `0700`, tmpfs) | `~/Library/Application Support/DataForge/engine.sock` (`0700`) | `\\.\pipe\dataforge-engine` (SDDL) | `runtime_dir` |
| **Data (exports)** | `~/Documents/DataForge` (user-visible, never auto-deleted) | same | same | `data_dir` |

**Implementation:** New `dataforge/core/paths.py` centralizes this. Everything else calls `paths.config_file`, `paths.cache_db`, etc. — no `os.path.expanduser("~/.dataforge")` scattered.

```python
# dataforge/core/paths.py — single source of truth
from platformdirs import PlatformDirs
dirs = PlatformDirs("DataForge", "DataForge")
config_file = dirs.user_config_path / "config.json"
cache_db    = dirs.user_cache_path / "cache.db"
jobs_db     = dirs.user_state_path / "jobs.db"
log_file    = dirs.user_state_path / "logs" / "app.log"
# + migration: if legacy ~/.dataforge exists and new location empty, move with backup
```

---

## 2. Versioning — One Number Everywhere

```
pyproject.toml: version = "0.2.0"          ← source of truth
dataforge/__init__.py: __version__ = "0.2.0"  ← runtime
dataforge/core/config.py: CONFIG_SCHEMA_VERSION = 2
dataforge/core/cache.py: PRAGMA user_version = 2  (SQLite)
installer: ProductVersion 0.2.0 (msi/pkg/deb)
engine --version / fm --version → same string
```

- Bump version in one place (`pyproject.toml`), CI syncs the rest via `scripts/bump_version.py`.
- `config.json` gets `"_schema_version": 2` top-level key. Loader migrates 1→2→3, never drops unknown future keys without warning.
- `cache.db` / `jobs.db` use `PRAGMA user_version`. On open, compare; run `migrations/{from}_{to}.sql` atomically; `VACUUM` only after success.

---

## 3. Packaging — What Ships Per OS

### 3.1 Matrix

| OS | Primary (recommended) | Alt (dev) | Service registration | Uninstall entry |
|---|---|---|---|---|
| **Linux** | `.deb` + `.rpm` (via `nfpm`/`fpm` or `cpack`) + `pipx`/`pip` wheel | `AppImage` / `Flatpak` (Flathub) | `systemd --user` `dataforge.socket` + `dataforge.service` + `com.dataforge.Engine.service` (D-Bus) via `postinst` | `apt remove` / `dnf remove` + `systemctl --user disable --now` in `prerm` |
| **Windows** | `.msi` (WiX v4) or `.msix` (Store-ready) | `winget` (`winget install DataForge.DataForge`), `scoop` | Windows Service `DataForgeEngine` (SCM) + Named Pipe, registered in `post-install` custom action | `Add/Remove Programs` → `UninstallString` `MsiExec /x`, custom action stops service + removes pipe |
| **macOS** | `.dmg` (drag to `/Applications`) + `.pkg` (for MDM) + `brew cask` | `pipx` | `launchd` `com.dataforge.engine.plist` + XPC helper (`SMJobBless`) | Drag to Trash *or* `brew uninstall` *or* `pkgutil --forget`; `postinstall` runs `launchctl bootstrap`, `prerm` runs `bootout` |

`build_exe.py` stays for **standalone bundle** (`DataForge` onefile + `DataForge-debug` onedir) but becomes an *input* to the installers, not the installer itself. The installers wrap the bundle + service files + desktop entry.

### 3.2 What Each Package Contains

```
dataforge_0.2.0_amd64.deb
  /usr/bin/dataforge                → shim to /opt/dataforge/DataForge
  /opt/dataforge/DataForge          ← PyInstaller onefile (or onedir for faster upgrades, see §5)
  /opt/dataforge/dataforge-engine   ← same, --engine mode
  /usr/share/applications/dataforge.desktop
  /usr/share/icons/hicolor/.../dataforge.png
  /usr/share/dbus-1/services/com.dataforge.Engine.service
  /usr/lib/systemd/user/dataforge.socket
  /usr/lib/systemd/user/dataforge.service
  DEBIAN/postinst → systemctl --user daemon-reload; enable --now (if user session)
  DEBIAN/prerm   → systemctl --user disable --now dataforge.socket dataforge.service

DataForge-0.2.0.msi
  %ProgramFiles%\DataForge\DataForge.exe
  %ProgramFiles%\DataForge\dataforge-engine.exe
  Service: DataForgeEngine (auto, delayed)
  Registry: HKLM\Software\DataForge\Version=0.2.0, InstallLocation
  ARP: DisplayName=DataForge 0.2.0, UninstallString, QuietUninstallString
  CustomAction post-install → sc create + sc start

DataForge-0.2.0.dmg
  /Applications/DataForge.app  (bundle: MacOS/DataForge, Resources, Info.plist CFBundleVersion 0.2.0)
  postinstall pkg script → launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.dataforge.engine.plist
```

---

## 4. Install / Upgrade / Remove — Exact Flows

### 4.1 Install (fresh)

1. Copy bin + service files to canonical locations (see §1, §3.2).
2. Create `config_dir`/`cache_dir`/`state_dir` if missing; **do not overwrite** existing `config.json`.
3. If legacy `~/.dataforge/` exists and new locations are empty → **migrate** (copy with backup `~/.dataforge.backup.$timestamp/`, set `migrated_from_legacy=true` in new config, log).
4. Run DB migrations: `PRAGMA user_version` → apply `migrations/*.sql` to `cache.db`/`jobs.db`.
5. Register service: `systemctl --user enable --now` / `sc create`+`start` / `launchctl bootstrap`.
6. Register desktop entry / Start Menu / Dock.

### 4.2 Upgrade (0.1.0 → 0.2.0 example)

Must be **atomic and rollback-safe**.

```
1. Stop engine but keep socket (systemd socket-activation buffers connects)
   - Linux: systemctl --user stop dataforge.service (socket stays)
   - Windows: sc stop DataForgeEngine
   - macOS: launchctl kickstart -k (keeps socket)

2. Replace bin atomically:
   - Use staging dir: /opt/dataforge.new/ or %ProgramFiles%\DataForge.new\
   - Verify signature/checksum, then rename: mv /opt/dataforge.new /opt/dataforge (atomic on same FS)
   - For onedir bundle: rsync + rename is faster than onefile rewrite (see §5)

3. Migrate data:
   - config.json: 1→2 (e.g., add hash_block_size, rename keys) — backup config.json.bak.<version>
   - cache.db: user_version 1→2 — ALTER TABLE ADD COLUMN st_ino, CREATE INDEX — in one transaction, VACUUM after

4. systemctl --user daemon-reload; start service; health check: dataforge-engine --health (tries UDS/pipe)

5. On failure: restore backup, daemon-reload, start old version, report to installer (MSI rollback, deb preinst failure)
```

**Never delete user exports** (`~/Documents/DataForge`, carve output) on upgrade.

### 4.3 Remove / Uninstall

Two modes (like `apt remove` vs `apt purge`):

| Mode | Flag | What is removed | What is kept (default) |
|---|---|---|---|
| **Remove** | `apt remove` / `msiexec /x` / drag to Trash | Bin, service files, desktop entry, socket/pipe. Stops service first (`prerm`: `disable --now`/`sc delete`/`bootout`). | `config_dir`, `cache_dir`, `state_dir`/`logs`, user exports. User can reinstall and keep settings. |
| **Purge** | `apt purge` / `msiexec /x + purge` / `brew uninstall --zap` / installer `--purge` | Everything above **plus** `config_dir`, `cache_dir`, `state_dir`, `logs`, runtime socket | Nothing. Exports under `~/Documents/DataForge` are **never** purged automatically — require explicit `fm clean --purge-exports` or manual delete. |

`prerm`/`postrm` (Linux), custom action `OnUninstall` (Windows), `preinstall`/`postinstall` (macOS pkg) must be idempotent — second `remove` after `purge` should not error.

### 4.4 Reinstall / Repair

`apt install --reinstall`, `msiexec /fa`, `brew reinstall` — same as upgrade but from same version. Re-registers service and desktop entry, re-runs DB `user_version` check (no-op if current).

---

## 5. PyInstaller Choice — Onefile vs Onedir for Upgrades

`build_exe.py:46` currently builds **onefile** (`--onefile --windowed`) for release — single `DataForge` exe that unpacks to temp on every launch.

| Bundle | Startup | Upgrade cost | When to use |
|---|---|---|---|
| **Onefile** | Slow (unpack to `$TMP/_MEI*`, 1-2s), large single file replace is atomic | Cheap to distribute (one file), but replace is full re-download | Good for portable `.zip` / USB triage stick |
| **Onedir** (`--onedir`) | Fast (no unpack), many small files | Faster incremental upgrades (rsync only changed libs, ~5-20% of bundle), but installer must handle many files | **Recommended for installed package** — unpack once at install, `rsync` on upgrade, no per-launch unpack |

**Recommendation:** Keep **both**:
- `dist/release/DataForge` (onefile) → publish as `DataForge-0.2.0-portable-*` for triage.
- `dist/onedir/DataForge/` (onedir) → used *inside* `.deb`/`.msi`/`.pkg` at `/opt/dataforge/` / `%ProgramFiles%` / `DataForge.app/Contents/Resources/`.

`build_exe.py` should produce both in CI; installers consume onedir.

---

## 6. Auto-Update (optional, but design for it now)

Even if first release is manual `apt upgrade`/`winget upgrade`, design so later you can add in-app update without rework.

```
Version source: https://updates.dataforge.dev/releases.json  { "latest":"0.2.1", "url":{...}, "sha256":{...}, "min_schema":2 }
Check: engine --check-update (called by GUI weekly, or systemd timer)
Download: to $XDG_CACHE_HOME/dataforge/updates/0.2.1.{deb,msi,dmg} + sha256 verify + sig verify (minisign)
Apply:
  - Linux (deb): pkexec apt install ./dataforge_0.2.1.deb  (or flatpak update)
  - Windows (msi/msix): MsiInstallProduct (elevated), or Sparkle/Squirrel if using those
  - macOS (dmg/pkg): Sparkle framework inside DataForge.app (standard, handles notarization, delta updates)
Rollback: keep previous bundle at /opt/dataforge.prev/ until next successful launch
```

Do **not** invent a custom updater that writes to `/usr` without elevation — use the OS package manager or Sparkle. Custom download-to-`~/.local` is only for `pipx`/`single-user` installs.

---

## 7. Migrations — Config + DB

### 7.1 Config migration (`config.json`)

```python
# dataforge/core/config.py — add
CONFIG_SCHEMA_VERSION = 2
MIGRATIONS = {
  1: lambda data: {**data, "_schema_version":2, "hash_block_size": 1<<20, "cache_batch_size": 1000},
  # 2→3: rename ... etc
}
def load():
    data = json.load(f)
    v = data.get("_schema_version", 1)  # legacy has no key → 1
    while v < CONFIG_SCHEMA_VERSION:
        data = MIGRATIONS[v](data)
        v += 1
    # then _merge_validated
    backup = config_file.with_suffix(f".bak.v{v_before}")
    shutil.copy2(config_file, backup)
    save(data)
```

### 7.2 DB migration (`cache.db`, `jobs.db`)

```sql
-- dataforge/migrations/cache_1_2.sql
PRAGMA journal_mode=WAL;
ALTER TABLE file_hashes ADD COLUMN st_ino INTEGER;
ALTER TABLE file_hashes ADD COLUMN st_dev INTEGER;
CREATE INDEX IF NOT EXISTS idx_hash_lookup ON file_hashes(algo, size, mtime);
PRAGMA user_version=2;
```

Engine opens DB → `PRAGMA user_version` → apply pending `*.sql` in one transaction → `VACUUM` on success.

---

## 8. What Changes in Code (checklist for PR)

- [ ] New `dataforge/core/paths.py` (platformdirs) — all direct `~/.dataforge` references go through it. Keep legacy path as fallback+migrate.
- [ ] `dataforge/core/config.py`: add `_schema_version`, `MIGRATIONS`, backup on write.
- [ ] `dataforge/core/cache.py` + new `engine/jobs.py`: `user_version` + `migrations/` dir.
- [ ] `dataforge/__init__.py`: `__version__` from `importlib.metadata.version("dataforge")` fallback to `pyproject.toml`.
- [ ] `pyproject.toml:30` bump packaging: add `platformdirs` to deps, add `[project.urls]` + `[project.scripts]` `dataforge-engine = dataforge.service.__main__:main`.
- [ ] `build_exe.py`: produce both `release` (onefile) and `onedir` profiles; embed `version.json` + `Info.plist` `CFBundleVersion`.
- [ ] New `packaging/` dir: `nfpm.yaml` (deb/rpm), `wix/` (msi), `dmg/` (create-dmg), `launchd/`/`systemd/` templates.
- [ ] New `scripts/bump_version.py` (syncs `pyproject.toml` / `__init__.py` / `Info.plist` / `wxs`).
- [ ] CI: build matrix `linux-deb`, `linux-rpm`, `windows-msi`, `macos-dmg+pkg`, sign (GPG/msi cert/Apple notarize).

---

## 9. Updated Roadmap (extends both previous docs)

| Phase | Ships | Effort | Covers |
|---|---|---|---|
| **I0. Paths + version + migrations** | `core/paths.py`, `CONFIG_SCHEMA_VERSION`, `PRAGMA user_version`, legacy `~/.dataforge` migration, `__version__` | S (3-4 days) | Installable without data loss — do this *before* any package |
| **I1. Onedir bundle + nfpm deb/rpm** | `build_exe.py` onedir, `packaging/nfpm.yaml`, `postinst`/`prerm` systemd units | S (1 wk) | `apt install ./dataforge.deb` → `systemctl --user status dataforge` works, `apt purge` cleans |
| **I2. Windows msi + macOS dmg/pkg** | WiX `Product.wxs`, `service/windows/service.py`, `launchd` plist, `brew cask` | M (1-1.5 wks) | `winget`/`brew` install, Add/Remove, drag-to-Trash |
| **I3. N0 engine + UDS/pipe** (from native doc) | `engine/daemon.py`, `api/transport/*`, `client/` | S (1.5 wks) | Native IPC, out-of-process engine |
| **I4. Auto-update** | `updates.json`, Sparkle (macOS), `systemd` timer / `winget` | M (1 wk) | `Check for updates` in GUI, delta updates |

Do **I0 first** — without `paths.py` + migrations, every later package will orphan `~/.dataforge` and break upgrades. I0 is 3-4 days and unblocks everything.

---

## 10. Decision Needed

1. **Package manager priority:** `deb`+`msi`+`dmg` first (covers 95%), or also `flatpak`/`brew` day one?
2. **Onefile vs onedir inside package:** Approve onedir-inside-package (fast upgrades) while keeping onefile for portable zip?
3. **Purge default:** Keep `remove` (keep config/cache) as default and `purge` as opt-in — matches `apt`/`brew --zap` expectation. Confirm?
