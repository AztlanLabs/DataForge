# DataForge Engine Migrations

**Wave:** 0 (contract) — `TICK-004` creates the directory and convention;
actual SQL migrations land in Wave 1 (`TICK-104`).

## Convention

* Location: `dataforge/engine/migrations/*.sql`
* Naming: `{from}_{to}.sql` or `{scope}_{from}_{to}.sql`
  (e.g. `cache_1_2.sql`, `1_2.sql`). Any `*.sql` is enumerated as pending
  when `PRAGMA user_version < CACHE_SCHEMA_VERSION`.
* Engine opens `cache.db` / `jobs.db`, reads `PRAGMA user_version`,
  enumerates pending `*.sql` via `CacheManager.get_pending_migrations()`,
  and (from Wave 1) applies them in version order inside a single
  transaction followed by `VACUUM` on success.

### Cache migrations (current: `CACHE_SCHEMA_VERSION = 2`)

Example `cache_1_2.sql` (applied in Wave 1, not yet):

```sql
PRAGMA journal_mode=WAL;
ALTER TABLE file_hashes ADD COLUMN st_ino INTEGER;
ALTER TABLE file_hashes ADD COLUMN st_dev INTEGER;
CREATE INDEX IF NOT EXISTS idx_hash_lookup ON file_hashes(algo, size, mtime);
PRAGMA user_version=2;
```

### Config migrations (current: `CONFIG_SCHEMA_VERSION = 2`)

Config migrations are Python callables in `dataforge/core/config.py:MIGRATIONS`
(e.g. `1: _migrate_v1_to_v2` adds `hash_block_size=1<<20`,
`cache_batch_size=1000`, `_schema_version=2` and creates
`config.json.bak.v1`). See `docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md` §7.1.

## Wave 0 status

* Directory exists, this README is the only committed file.
* No `*.sql` files are shipped yet — tests may create ephemeral ones.
* `CacheManager` enumerates pending `*.sql` (via `get_pending_migrations()`
  / `pending_migrations`) but does **not** yet apply them.

## Wave 1 (TICK-104) will

* Add `cache_1_2.sql` and implement `set_hash_many` with `executemany`.
* Add `PRAGMA synchronous=NORMAL`, `cache_size=-64000`, and
  `idx_hash_lookup` index creation.
* Execute pending migrations on open.

See also: `docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md` §7–§8,
`docs/PARALLEL_BACKLOG.md` TICK-004 / TICK-104.
