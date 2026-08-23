import json
import os
import shutil
from typing import Any, Callable, Dict
from .logger import logger

_VALID_HASH_ALGORITHMS = {"md5", "sha1", "sha256", "sha512", "blake2b"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_SIZE_UNITS = {"Auto", "Bytes", "KB", "MB", "GB"}
_VALID_PATH_MODES = {"full", "relative"}
_VALID_TIERS = {"Simple", "Standard", "Everything"}

# ---------------------------------------------------------------------------
# Schema versioning — INSTALL_UPGRADE_LIFECYCLE §7.1
# ---------------------------------------------------------------------------
CONFIG_SCHEMA_VERSION: int = 2


def _cpu_count() -> int:
    try:
        c = os.cpu_count()
        return c if c is not None else 4
    except Exception:
        return 4


def _default_max_thread_workers() -> int:
    return min(32, _cpu_count() * 4)


def _default_search_thread_workers() -> int:
    return min(32, _cpu_count() * 2)


def _migrate_v1_to_v2(data: dict) -> dict:
    """Migrate config from schema v1 (no _schema_version) to v2.

    Adds adaptive worker defaults and new performance keys if missing.
    """
    migrated = dict(data)
    migrated["_schema_version"] = 2
    if "hash_block_size" not in migrated:
        migrated["hash_block_size"] = 1 << 20
    if "cache_batch_size" not in migrated:
        migrated["cache_batch_size"] = 1000
    return migrated


MIGRATIONS: Dict[int, Callable[[dict], dict]] = {
    1: _migrate_v1_to_v2,
}


class ConfigManager:
    _instance = None

    DEFAULT_CONFIG = {
        "theme": "cosmo",
        "safe_mode": True,
        "excluded_extensions": [".tmp", ".log"],
        "excluded_folders": [".git", "node_modules", "__pycache__"],
        "max_thread_workers": _default_max_thread_workers(),
        "search_thread_workers": _default_search_thread_workers(),
        "hash_algorithm": "sha256",
        "log_level": "INFO",
        "size_unit": "Auto",
        "path_display_mode": "full",
        "dashboard_paths": [os.path.join(os.path.expanduser("~"), "Documents")],
        "settings_ui_tier": "Simple",
        "duplicate_default_keep_strategy": "first path",
        "plugins_enabled": False,
        "ui_reduce_motion": False,
        "hash_block_size": 1 << 20,
        "cache_batch_size": 1000,
        "_schema_version": CONFIG_SCHEMA_VERSION,
    }

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, config_file: str | None = None, config_dir: str | None = None):
        if hasattr(self, 'initialized') and config_file is None:
            return
        if hasattr(self, 'initialized') and config_file is not None:
            self.config_file = config_file
            self.config_dir = config_dir or os.path.dirname(config_file) or os.path.join(
                os.path.expanduser("~"), ".dataforge"
            )
            self.data = self.DEFAULT_CONFIG.copy()
            self.data["max_thread_workers"] = _default_max_thread_workers()
            self.data["search_thread_workers"] = _default_search_thread_workers()
            self.load()
            return
        if config_file is not None:
            self.config_file = config_file
            self.config_dir = config_dir or os.path.dirname(config_file) or os.path.join(
                os.path.expanduser("~"), ".dataforge"
            )
        else:
            try:
                from .paths import config_file as _pf, config_dir as _pd

                self.config_file = str(_pf)
                self.config_dir = str(_pd)
            except ImportError:
                try:
                    from dataforge.core.paths import config_file as _pf2, config_dir as _pd2

                    self.config_file = str(_pf2)
                    self.config_dir = str(_pd2)
                except ImportError:
                    self.config_dir = os.path.join(os.path.expanduser("~"), ".dataforge")
                    self.config_file = os.path.join(self.config_dir, "config.json")
        self.data = self.DEFAULT_CONFIG.copy()
        self.data["max_thread_workers"] = _default_max_thread_workers()
        self.data["search_thread_workers"] = _default_search_thread_workers()
        self.data["_schema_version"] = CONFIG_SCHEMA_VERSION
        self.load()
        self.initialized = True

    def load(self):
        """Load config from disk, handling schema migration (1→2).

        Legacy files without ``_schema_version`` are treated as v1.
        Migration creates ``config.json.bak.v1`` and fills new keys.
        """
        if not os.path.exists(self.config_file):
            self.data = self.DEFAULT_CONFIG.copy()
            self.data["max_thread_workers"] = _default_max_thread_workers()
            self.data["search_thread_workers"] = _default_search_thread_workers()
            self.data["_schema_version"] = CONFIG_SCHEMA_VERSION
            self.save()
            return
        try:
            with open(self.config_file, 'r') as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    return
                v = loaded.get("_schema_version", 1)
                if not isinstance(v, int) or v < 1:
                    v = 1
                if v < CONFIG_SCHEMA_VERSION:
                    try:
                        backup_path = self.config_file + f".bak.v{v}"
                        shutil.copy2(self.config_file, backup_path)
                    except OSError:
                        pass
                    data = dict(loaded)
                    cur_v = v
                    while cur_v < CONFIG_SCHEMA_VERSION:
                        migrator = MIGRATIONS.get(cur_v)
                        if migrator is not None:
                            data = migrator(data)
                        else:
                            data["_schema_version"] = cur_v + 1
                        nxt = data.get("_schema_version", cur_v + 1)
                        if not isinstance(nxt, int) or nxt <= cur_v:
                            nxt = cur_v + 1
                            data["_schema_version"] = nxt
                        cur_v = nxt
                    self.data = self.DEFAULT_CONFIG.copy()
                    self.data["max_thread_workers"] = _default_max_thread_workers()
                    self.data["search_thread_workers"] = _default_search_thread_workers()
                    self.data["_schema_version"] = CONFIG_SCHEMA_VERSION
                    self._merge_validated(data)
                    self.data["_schema_version"] = CONFIG_SCHEMA_VERSION
                    for k in ("hash_block_size", "cache_batch_size", "_schema_version"):
                        if k in data and k not in self.data:
                            self.data[k] = data[k]
                        elif k in data and self.data.get(k) == self.DEFAULT_CONFIG.get(k):
                            if self._validate_one(k, data[k], self.DEFAULT_CONFIG.get(k)):
                                self.data[k] = data[k]
                    self.save()
                    return
                self._merge_validated(loaded)
                if "_schema_version" in loaded and isinstance(loaded["_schema_version"], int):
                    self.data["_schema_version"] = loaded["_schema_version"]
                else:
                    self.data["_schema_version"] = CONFIG_SCHEMA_VERSION
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load config: {e}")

    def _merge_validated(self, loaded: dict):
        for key, default_val in self.DEFAULT_CONFIG.items():
            if key not in loaded:
                continue
            val = loaded[key]
            if not self._validate_one(key, val, default_val):
                continue
            self.data[key] = val
        # Preserve unknown keys (user-defined, plugins, collapsed_groups, etc.)
        for key, val in loaded.items():
            if key not in self.DEFAULT_CONFIG:
                self.data[key] = val

    def _validate_one(self, key: str, val: Any, default: Any) -> bool:
        if key in ("max_thread_workers", "search_thread_workers"):
            if not isinstance(val, int) or val < 1 or val > 256:
                return False
            return True
        if key == "hash_block_size":
            if not isinstance(val, int) or val < 1024 or val > 16 * 1024 * 1024:
                return False
            return True
        if key == "cache_batch_size":
            if not isinstance(val, int) or val < 1 or val > 100000:
                return False
            return True
        if key == "_schema_version":
            if not isinstance(val, int) or val < 1 or val > 100:
                return False
            return True
        if key == "hash_algorithm":
            return isinstance(val, str) and val.lower() in _VALID_HASH_ALGORITHMS
        if key == "log_level":
            return isinstance(val, str) and val.upper() in _VALID_LOG_LEVELS
        if key == "size_unit":
            return isinstance(val, str) and val in _VALID_SIZE_UNITS
        if key == "path_display_mode":
            return isinstance(val, str) and val in _VALID_PATH_MODES
        if key == "settings_ui_tier":
            return isinstance(val, str) and val in _VALID_TIERS
        if key in ("safe_mode", "plugins_enabled", "ui_reduce_motion"):
            return isinstance(val, bool)
        if key in ("excluded_extensions", "excluded_folders", "dashboard_paths"):
            return isinstance(val, list)
        if key == "theme":
            return isinstance(val, str) and len(val) > 0
        if key == "duplicate_default_keep_strategy":
            return isinstance(val, str)
        return isinstance(val, type(default))

    def save(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.data, f, indent=4)
        except OSError as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()

config = ConfigManager()
