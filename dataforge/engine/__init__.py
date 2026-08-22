"""
DataForge engine package — Wave 0 contract.

This package is the future home of the out-of-process engine
(``engine/daemon.py``, ``engine/jobs.py``, ``engine/index.py``) and
DB migrations (``engine/migrations/*.sql``).

Wave 0 (TICK-004) provides the persistence contracts only:

* :data:`dataforge.core.config.CONFIG_SCHEMA_VERSION` (current: 2)
* :data:`dataforge.core.cache.CACHE_SCHEMA_VERSION` (current: 2)
* ``PRAGMA user_version`` enumeration via :meth:`dataforge.core.cache.CacheManager.get_pending_migrations`
* :meth:`dataforge.core.cache.CacheManager.set_hash_many` stub signature
* Adaptive defaults (``max_thread_workers``, ``search_thread_workers``,
  ``hash_block_size=1<<20``, ``cache_batch_size=1000``)

Wave 1 (TICK-104) will fill the batched ``executemany``, index creation,
and migration execution. See ``dataforge/engine/migrations/README.md``
and ``docs/proposals/INSTALL_UPGRADE_LIFECYCLE.md`` §7.
"""

from pathlib import Path

MIGRATIONS_DIR: Path = Path(__file__).resolve().parent / "migrations"

__all__ = ["MIGRATIONS_DIR"]
