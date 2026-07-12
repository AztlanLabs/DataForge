import os
import stat
import importlib.util
import importlib
import sys
import glob
import platform
from typing import List, Type
from .views.base import BaseView
from ..core.logger import logger

class PluginLoader:
    def __init__(self, plugin_dir: str, enabled: bool = False):
        self.plugin_dir = plugin_dir
        self.enabled = enabled

    def load_plugins(self) -> List[Type[BaseView]]:
        """
        Scans plugin directory for python files.
        Imports them and looks for BaseView subclasses.

        Plugin loading is opt-in (``enabled=True``). When disabled, no code is
        executed from the plugin directory. Each successful load is logged.
        """
        plugins = []
        if not self.enabled:
            logger.debug("Plugin loading is disabled (set enabled=True to opt in).")
            return plugins

        if not os.path.exists(self.plugin_dir):
            return plugins

        if not self._check_plugin_dir_permissions():
            logger.warning(
                f"Plugin directory {self.plugin_dir} has unsafe permissions; "
                "skipping plugin load."
            )
            return plugins

        files = glob.glob(os.path.join(self.plugin_dir, "*.py"))

        for file_path in files:
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            if module_name.startswith("__"):
                continue

            if not self._check_plugin_file_owner(file_path):
                logger.warning(f"Skipping plugin {module_name}: not owned by current user.")
                continue

            package_name = "dataforge.ui.plugins"
            full_module_name = f"{package_name}.{module_name}"
            try:
                importlib.import_module(package_name)
            except Exception:
                pass

            spec = importlib.util.spec_from_file_location(full_module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[full_module_name] = module
                try:
                    spec.loader.exec_module(module)
                    logger.info(f"Loaded plugin: {module_name} from {file_path}")

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and
                            issubclass(attr, BaseView) and
                            attr is not BaseView):
                            plugins.append(attr)
                except Exception as e:
                    logger.error(f"Failed to load plugin {module_name}: {e}")

        return plugins

    def _check_plugin_dir_permissions(self):
        """Warn if the plugin directory is world-writable."""
        if platform.system() == "Windows":
            return True
        try:
            mode = os.stat(self.plugin_dir).st_mode
            if mode & stat.S_IWOTH:
                logger.warning(
                    f"Plugin directory {self.plugin_dir} is world-writable "
                    f"(mode {oct(mode)})."
                )
                return False
        except OSError:
            pass
        return True

    def _check_plugin_file_owner(self, file_path):
        """On Unix, verify the plugin file is owned by the current user."""
        if platform.system() == "Windows":
            return True
        try:
            file_stat = os.stat(file_path)
            return file_stat.st_uid == os.getuid()
        except OSError:
            return False
