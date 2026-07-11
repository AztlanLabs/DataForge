import json
import os
from typing import Any, Dict
from .logger import logger

class ConfigManager:
    _instance = None
    
    DEFAULT_CONFIG = {
        "theme": "cosmo",
        "safe_mode": True,  # Use trash bin
        "excluded_extensions": [".tmp", ".log"],
        "excluded_folders": [".git", "node_modules", "__pycache__"],
        # Separate worker-count budgets per operation category, so a user can
        # e.g. keep hashing single-threaded on a low-power machine while still
        # parallelizing search, or vice versa, rather than one shared knob
        # that silently only ever governed duplicate-file hashing.
        "max_thread_workers": 4,       # hashing/batch work: duplicates, forensics hash manifests, integrity snapshots, metadata batch reads
        "search_thread_workers": 4,    # search/keyword-search parallel scanning
        # SHA-256 by default: MD5 is collision-prone, and duplicate detection
        # can delete files that merely share a digest. Users may still opt into
        # md5/sha1 for speed via Settings.
        "hash_algorithm": "sha256",
        "log_level": "INFO",
        "size_unit": "Auto", # Auto, Bytes, KB, MB, GB
        "path_display_mode": "full",  # "full" or "relative" (relative to each view's scan/source folder)
        "dashboard_paths": [os.path.join(os.path.expanduser("~"), "Documents")],
        "settings_ui_tier": "Basic",  # Basic, Advanced, Expert
        "duplicate_default_keep_strategy": "first path",
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
                self.data.update(loaded)
            logger.info(f"Configuration loaded from {self.config_file}")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load config: {e}")

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

# Global instance
config = ConfigManager()
