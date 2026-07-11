import os
import importlib.util
import importlib
import sys
import glob
from typing import List, Type
from .views.base import BaseView
from ..core.logger import logger

class PluginLoader:
    def __init__(self, plugin_dir: str):
        self.plugin_dir = plugin_dir

    def load_plugins(self) -> List[Type[BaseView]]:
        """
        Scans plugin directory for python files.
        Imports them and looks for BaseView subclasses.
        """
        plugins = []
        if not os.path.exists(self.plugin_dir):
            return plugins
            
        # Get all .py files
        files = glob.glob(os.path.join(self.plugin_dir, "*.py"))
        
        for file_path in files:
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            if module_name.startswith("__"):
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
                    
                    # Inspect module for View classes
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseView) and 
                            attr is not BaseView):
                            plugins.append(attr)
                except Exception as e:
                    logger.error(f"Failed to load plugin {module_name}: {e}")
                    
        return plugins
