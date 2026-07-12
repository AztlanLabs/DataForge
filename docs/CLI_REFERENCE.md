# 🔨 DataForge CLI Reference

*File System Management with Steroids and Superpowers*

## Entry Point — CLI Superpowers

The CLI is exposed as:

```bash
fm
```

If you are working directly from source without an editable install, run:

```bash
PYTHONPATH=. python -m dataforge.cli
```

## Command map

| Command | Purpose |
| --- | --- |
| `scan` | List scanned files |
| `dupes` | Find duplicate files and optionally export reports |
| `search` | Search files by name, extension, size, age, or content |
| `organize` | Move or copy filtered results into a destination |
| `rename` | Bulk rename files using regex replacement |
| `clean` | Remove empty folders |
| `usage` | Produce a disk-usage report |
| `integrity create` | Create a snapshot of file hashes |
| `integrity check` | Compare the current state against a snapshot |
| `cleanup` | Scan and remove junk/cache files by category |
| `performance` | Show process, startup-item, and disk-health diagnostics |
| `recover` | Restore files from trash or carve them from a disk image |
| `metadata` | Read, edit, or strip file metadata (including GPS fields) |
| `hardware` | Show hardware diagnostics and upgrade recommendations |
| `forensics` | Parse OS artifacts, keyword-search files, or list file-signature categories |
| `hash-calc` | Calculate cryptographic hashes of files |
| `devices` | List connected storage devices and their usage |

## `fm scan`

```bash
fm scan PATH [--recursive/--no-recursive]
```

Lists files discovered by the shared scanner.

### Notes

- `PATH` must exist.
- Recursion is enabled by default.

### Example

```bash
fm scan ~/Documents --no-recursive
```

## `fm dupes`

```bash
fm dupes PATH [options]
```

Finds duplicate files by content hash.

### Important options

- `--max-depth N` - limit scan depth, `-1` means unlimited
- `--sort group|ext|path|name|size|created|modified`
- `--reverse`
- `--limit N`
- `--format text|json|jsonl`
- `--output PATH`
- `--export-format csv|json|txt`
- `--flat-export` - omit group summary rows for CSV/JSON exports
- `--count-only` - emit only the duplicate-row count

### Behavior

- The command prints a summary before the actual rows unless `--count-only` is used.
- JSON and JSONL emit serialized duplicate records.
- Export format defaults from the output filename when possible.

### Examples

```bash
fm dupes ~/Downloads --sort group --reverse --limit 20
fm dupes ~/Archive --count-only
fm dupes ~/Photos --format jsonl
fm dupes ~/Media --output duplicates.csv --export-format csv
fm dupes ~/Media --output duplicates.json --flat-export
```

## `fm search`

```bash
fm search PATH [options]
```

Searches files with a reusable query model shared by the GUI.

### Name and content filters

- `--name-glob PATTERN`
- `--name-regex PATTERN`
- `--ext jpg,png,pdf`
- `--content TEXT`
- `--content-regex`
- `--case-sensitive`

### Size and age filters

- `--min-size BYTES`
- `--max-size BYTES`
- `--newer-than-days N`
- `--older-than-days N`
- `--max-depth N`

### Output and scripting options

- `--sort ext|path|name|size|created|modified`
- `--reverse`
- `--limit N`
- `--format text|json|jsonl`
- `--error-format text|json`
- `--count-only`

### Important behavior

- `--name-glob` and `--name-regex` are mutually exclusive.
- With `--error-format json`, invalid combinations are emitted as machine-readable JSON errors to stderr with exit code `2`.
- `--count-only` overrides normal output formatting and prints only the final count.
- Sorted output forces the command to materialize results before emitting them.

### Examples

```bash
fm search ~/Documents --name-glob "*.pdf"
fm search ~/Code --content "TODO" --case-sensitive
fm search ~/Photos --ext jpg,png --sort size --reverse --limit 20
fm search ~/Logs --name-regex "app-.*\\.log" --format json
fm search ~/Docs --count-only
```

## `fm organize`

```bash
fm organize PATH --dest DEST [--action move|copy] [--name REGEX] [--ext LIST] [--dry-run/--execute]
```

Organizes matching files into a destination folder.

### Options

- `--dest DEST` - required target path
- `--action move|copy` - defaults to `copy`
- `--name REGEX` - filename regex filter
- `--ext jpg,png,pdf` - extension filter
- `--dry-run/--execute` - defaults to preview mode (`--dry-run`)

### Example

```bash
fm organize ~/Downloads --dest ~/Sorted --action move --ext pdf,docx --execute
```

## `fm rename`

```bash
fm rename PATH --pattern REGEX --repl TEXT [--dry-run/--execute]
```

Bulk renames files with a regex replacement.

### Options

- `--pattern` - required regex pattern
- `--repl` - required replacement string
- `--dry-run/--execute` - defaults to preview mode

### Example

```bash
fm rename ~/Scans --pattern " " --repl "_" --execute
```

## `fm clean`

```bash
fm clean PATH [--dry-run/--execute]
```

Removes empty folders.

### Example

```bash
fm clean ~/Projects --execute
```

## `fm usage`

```bash
fm usage PATH
```

Produces a usage report using the `usage` module.

### Example

```bash
fm usage ~/Media
```

## `fm integrity create`

```bash
fm integrity create PATH SNAPSHOT
```

Creates a self-describing JSON snapshot for later verification. The snapshot is `{"algorithm": ..., "created_at": ..., "files": {relative_path: hash}}` and uses the configured `hash_algorithm` (default `sha256`); legacy flat `{path: md5}` snapshots are still readable by `integrity check`. See [`reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) (M4, S1).

### Example

```bash
fm integrity create ~/Records snapshots/records.json
```

## `fm integrity check`

```bash
fm integrity check PATH SNAPSHOT
```

Verifies the current file set against a previously created snapshot.

### Behavior

- Prints a success message when no discrepancies are found.
- Otherwise prints each discrepancy line by line.

### Example

```bash
fm integrity check ~/Records snapshots/records.json
```

## `fm cleanup`

```bash
fm cleanup [--path PATH] [--category CATEGORY]... [--min-age DAYS] [--dry-run/--execute]
```

Scans for and optionally removes junk/cache files across known categories.

### Options

- `--path PATH` - additional path to scan alongside default locations
- `--category, -c CATEGORY` - repeatable; restrict the scan to specific categories (default: all)
- `--min-age DAYS` - only include files older than N days
- `--dry-run/--execute` - defaults to preview mode (`--dry-run`)

Category names are matched **exactly** (case-sensitive) against the platform's category keys: `System Temp`, `User Cache`, `Thumbnails`, `Trash`, `Log Files`, `Package Cache`, `Crash Reports`. A name that doesn't match one of these scans nothing.

> [!CAUTION]
> Files under `System Temp` (`/tmp`, `/var/tmp`), `User Cache`, `Thumbnails`, `Trash`, and `Crash Reports` are treated as junk **regardless of type**, and any `--path` you pass is folded into that blanket classification. With `--execute` this can remove in-use temp files/sockets of other running processes, or everything inside a folder you point `--path` at. Always review the `--dry-run` output first. See [`reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) (S7).

### Example

```bash
fm cleanup --category "User Cache" --min-age 30 --execute
```

## `fm performance`

```bash
fm performance [--processes] [--startup] [--disk-health]
```

Shows system performance diagnostics. With no flags, prints a system overview (OS, CPU, RAM, uptime).

### Options

- `--processes` - list top resource-heavy processes by memory
- `--startup` - list system startup items
- `--disk-health` - check disk S.M.A.R.T. health status

### Example

```bash
fm performance --processes
```

## `fm recover`

```bash
fm recover [--trash] [--restore-trash] [--carve PATH --out DIR] [--types LIST]
```

Recovers deleted files from the system trash or carves file types from a disk image.

### Options

- `--trash` - scan the system trash
- `--restore-trash` - restore all scanned trash items (requires `--trash`, prompts for confirmation)
- `--carve PATH` - carve files from a disk image or device path
- `--out DIR` - required output directory when using `--carve`
- `--types jpg,png,pdf` - restrict carving to specific extensions

> [!CAUTION]
> `--restore-trash` restores files to the original path recorded in each item's `.trashinfo` metadata. When scanning trash on removable media, that path is attacker-controllable, so restore can write outside the expected location. Prefer restoring to a dedicated folder and reviewing targets first — see [`reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) (S4).

### Example

```bash
fm recover --carve /dev/sdb1 --out ~/Recovered --types jpg,png
```

## `fm metadata`

```bash
fm metadata PATH [--edit FIELD=VALUE] [--strip] [--strip-gps]
```

Reads, edits, or strips metadata from a single file.

### Options

- `--edit FIELD=VALUE` - set a single metadata field
- `--strip` - remove all metadata
- `--strip-gps` - remove only GPS/location fields
- (no option) - read and print metadata fields

### Example

```bash
fm metadata photo.jpg --strip-gps
```

## `fm hardware`

```bash
fm hardware [--export json|html --out PATH]
```

Prints a hardware profile (OS, motherboard, CPU, RAM, storage, GPU) and upgrade recommendations, or exports the report.

### Example

```bash
fm hardware --export json --out hardware.json
```

## `fm forensics`

```bash
fm forensics [PATH] [--parse-artifacts] [--search-keyword TEXT] [--list-types]
```

Forensic utilities for OS artifact parsing, keyword search, and file-signature lookup.

### Options

- `--parse-artifacts` - parse OS artifacts under `PATH`
- `--search-keyword TEXT` - search for a keyword under `PATH`
- `--list-types` - list known file-signature categories (from `dataforge/modules/file_signatures.py`); `PATH` is not required with this flag

### Example

```bash
fm forensics --list-types
fm forensics ~/Evidence --search-keyword "confidential"
```

## `fm hash-calc`

```bash
fm hash-calc PATH... [--algo md5|sha1|sha256|sha512]
```

Calculates cryptographic hashes for one or more files. All four algorithms are supported (`core/hasher.py` also implements `blake2b` internally); the earlier `sha512` crash is fixed — see [`reviews/AUDIT_FINDINGS.md`](./reviews/AUDIT_FINDINGS.md) (M1).

### Example

```bash
fm hash-calc file1.bin file2.bin --algo sha256
```

## `fm devices`

```bash
fm devices [--info MOUNTPOINT]
```

Lists connected storage devices (internal, external, USB, network, optical) with usage stats, backed by `dataforge/modules/device_manager.py`.

### Options

- `--info MOUNTPOINT` - show detailed usage info for a single mount point instead of the full table

### Example

```bash
fm devices
fm devices --info /mnt/data
```

## Automation notes

- Prefer `--format json` or `--format jsonl` for structured downstream processing.
- Prefer `search --error-format json` when integrating the CLI with automation that needs machine-readable usage failures.
- Use `--count-only` when the workflow only needs counts and not row data.

## Related documents

- [Project overview](../README.md)
- [Architecture](./ARCHITECTURE.md)
- [GUI workflows](./GUI_WORKFLOWS.md)
- [Project review (bugs, security, UX, roadmap)](./reviews/00_EXECUTIVE_SUMMARY.md)
