import json
from typing import List, Dict
from ..core.common import FileEntry
import pandas as pd

class ReportGenerator:
    @staticmethod
    def duplicates_to_csv(duplicates: Dict[str, List[FileEntry]], output_file: str):
        rows = []
        for hash_val, entries in duplicates.items():
            for entry in entries:
                rows.append({
                    'hash': hash_val,
                    'path': entry.path,
                    'size_bytes': entry.size,
                    'filename': entry.filename,
                    'extension': entry.extension
                })
        
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(output_file, index=False)
    
    @staticmethod
    def duplicates_to_json(duplicates: Dict[str, List[FileEntry]], output_file: str):
        data = {}
        for hash_val, entries in duplicates.items():
            data[hash_val] = [
                {
                    'path': e.path,
                    'size': e.size,
                    'filename': e.filename
                } for e in entries
            ]
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=4)
            
    @staticmethod
    def duplicates_to_txt(duplicates: Dict[str, List[FileEntry]], output_file: str):
        with open(output_file, 'w') as f:
            for hash_val, entries in duplicates.items():
                f.write(f"Hash: {hash_val} (Size: {entries[0].size} bytes)\n")
                for e in entries:
                    f.write(f"  - {e.path}\n")
                f.write("\n")
