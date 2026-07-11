import os
from collections import defaultdict
from ..core.scanner import scan_directory
from ..core.utils import format_size

def analyze_size(path: str) -> dict:
    """
    Analyze disk usage by folder.
    Returns a dict mapping folder_path -> total_size_bytes.
    """
    usage = defaultdict(int)
    for entry in scan_directory(path, recursive=True):
        folder = os.path.dirname(entry.path)
        usage[folder] += entry.size
        
        # Propagate up to parents?
        # For a simple view, just immediate parent is enough, 
        # or we simply aggregate by subdir of the root.
        
    return dict(usage)

def generate_usage_report(data: dict, limit: int = 20) -> list[str]:
    """
    Generate an ASCII bar chart of folders.
    """
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)[:limit]
    lines = []
    if not sorted_data:
        return ["No files found."]
        
    max_val = sorted_data[0][1]
    
    for folder, size in sorted_data:
        width = 50
        bar_len = int((size / max_val) * width) if max_val > 0 else 0
        bar = "#" * bar_len
        readable_size = format_size(size)
        lines.append(f"{folder} : {readable_size}")
        lines.append(f"[{bar:<{width}}]")
        
    return lines
