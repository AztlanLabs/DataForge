import json
import os
from typing import Any, Dict
from .logger import logger

_VALID_HASH_ALGORITHMS = {"md5", "sha1", "sha256", "sha512", "blake2b"}
_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_SIZE_UNITS = {"Auto", "Bytes", "KB", "MB", "GB"}
_VALID_PATH_MODES = {"full", "relative"}
_VALID_TIERS = {"Simple", "Standard", "Everything"}


class ConfigManager:
    _instance = None

    DEFAULT_CONFIG = {
        "theme": "cosmo",
        "safe_mode": True,
        "excluded_extensions": [".tmp", ".log"],
        "excluded_folders": [".git", "node_modules", "__pycache__"],
        "max_thread_workers": 4,
        "search_thread_workers": 4,
        "hash_algorithm": "sha256",
        "log_level": "INFO",
        "size_unit": "Auto",
        "path_display_mode": "full",
        "dashboard_paths": [os.path.join(os.path.expanduser("~"), "Documents")],
        "settings_ui_tier": "Simple",
        "duplicate_default_keep_strategy": "first path",
        "plugins_enabled": False,
        # 2e.3 accessibility — when True, every ``QPropertyAnimation``
        # in the app (sidebar collapse, view crossfade) runs with a
        # zero duration so the transition is instantaneous. Honors the
        # OS-level "reduce motion" preference for users who experience
        # motion sickness or vestibular issues from animated UI.
        "ui_reduce_motion": False,
    }

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        self.config_dir = os.path.join(os.path.expanduser("~"), ".dataforge")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.data: Dict[str, Any] = self.DEFAULT_CONFIG.copy()

        self.load()
        self.initialized = True

    def load(self):
        """Load config from disk."""
        if not os.path.exists(self.config_file):
            logger.info("No config file found, creating default.")
            self.save()
            return

        try:
            with open(self.config_file, 'r') as f:
                loaded = json.load(f)
                if not isinstance(loaded, dict):
                    logger.warning("Config file is not a JSON object; using defaults.")
                    return
                self._merge_validated(loaded)
            logger.info(f"Configuration loaded from {self.config_file}")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load config: {e}")

    def _merge_validated(self, loaded: dict):
        """Merge *loaded* into ``self.data`` after validating types, ranges,
        and enums. Unknown keys are silently dropped; invalid values are
        replaced with defaults."""
        for key, default_val in self.DEFAULT_CONFIG.items():
            if key not in loaded:
                continue
            val = loaded[key]
            if not self._validate_one(key, val, default_val):
                logger.warning(
                    f"Config key {key!r} has invalid value {val!r}; "
                    f"using default {default_val!r}."
                )
                continue
            self.data[key] = val

    def _validate_one(self, key: str, val: Any, default: Any) -> bool:
        """Return True when *val* is acceptable for *key*."""
        if key in ("max_thread_workers", "search_thread_workers"):
            if not isinstance(val, int) or val < 1 or val > 256:
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
        """Save config to disk."""
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.data, f, indent=4)
            logger.info("Configuration saved.")
        except OSError as e:
            logger.error(f"Failed to save config: {e}")

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        self.data[key] = value
        self.save()

config = ConfigManager()
