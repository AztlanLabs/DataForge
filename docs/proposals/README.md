# Proposals — Future Architecture (Not Yet Implemented)

These three documents describe **future work**. They are well-researched proposals against `dataforge/` HEAD at 2026-08-22, but the code they propose **does not exist yet**. Current truth lives in `../APP_REFERENCE.md`, `../ARCHITECTURE.md`, `../CLI_REFERENCE.md`, `../GUI_WORKFLOWS.md`, `../TECHNICAL_SOURCE_OF_TRUTH.md`.

| Proposal | What it proposes | Depends on |
|---|---|---|
| [`PERFORMANCE_INVESTIGATION.md`](./PERFORMANCE_INVESTIGATION.md) | Make it ridiculously fast: parallel scanner, batched cache, mmap hashing, pipelined dupes/search | — |
| [`NATIVE_OS_API_REVIEW.md`](./NATIVE_OS_API_REVIEW.md) | Native OS service + IPC: UDS/Named Pipes + D-Bus/XPC/COM, hybrid with HTTP for remote | `PERFORMANCE_INVESTIGATION` §3 (supersedes its FastAPI-only sketch) |
| [`INSTALL_UPGRADE_LIFECYCLE.md`](./INSTALL_UPGRADE_LIFECYCLE.md) | Installable/removable/upgradable as a real OS package: XDG/AppData, versioned migrations, deb/rpm/msi/dmg | `NATIVE_OS_API_REVIEW` I0 (`core/paths.py`) |

Read them in that order. Each file carries a `Status: PROPOSAL` banner at the top.
