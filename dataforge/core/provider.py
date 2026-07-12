from abc import ABC, abstractmethod
import shutil

class FileProvider(ABC):
    @abstractmethod
    def list_files(self, path: str, recursive: bool = True):
        pass

    @abstractmethod
    def move(self, src: str, dst: str):
        pass
    
    @abstractmethod
    def copy(self, src: str, dst: str):
        pass

class LocalProvider(FileProvider):
    def list_files(self, path: str, recursive: bool = True):
        # We can reuse our existing scanner here if we adapt it,
        # or implement simple logic.
        from .scanner import scan_directory
        return scan_directory(path, recursive)
    
    def move(self, src: str, dst: str):
        shutil.move(src, dst)
        
    def copy(self, src: str, dst: str):
        shutil.copy2(src, dst)
