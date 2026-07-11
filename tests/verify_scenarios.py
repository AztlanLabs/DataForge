import sys
import os
sys.path.append(os.getcwd())
import shutil
import unittest
from dataforge.modules.duplicates import find_duplicates
from dataforge.modules.search import SearchQuery, search_files
from dataforge.modules.renamer import bulk_rename
from dataforge.modules.cleaner import remove_empty_folders
from dataforge.modules.organizer import Organizer
from dataforge.modules.integrity import IntegrityMonitor

TEST_DIR = "test_env"

class TestDataForge(unittest.TestCase):
    def setUp(self):
        # Setup clean environment
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
        os.makedirs(TEST_DIR)
        
        # Create some files
        self.create_file("file1.txt", "content A")
        self.create_file("file2.txt", "content A") # duplicate
        self.create_file("file3.jpg", "content B")
        self.create_file("sub/file4.txt", "content C")
        
        # Create empty folders
        os.makedirs(os.path.join(TEST_DIR, "empty_dir"))
        os.makedirs(os.path.join(TEST_DIR, "deep/empty"))
        
    def create_file(self, path, content):
        full_path = os.path.join(TEST_DIR, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
            
    def tearDown(self):
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
            
    def test_duplicates(self):
        dups = find_duplicates(TEST_DIR)
        # file1 and file2 should be dupes
        self.assertTrue(len(dups) >= 1)
        # Check that we found the hash for 'content A'
        
    def test_search(self):
        query = SearchQuery().set_extensions(['txt'])
        results = search_files(TEST_DIR, query)
        # file1, file2, file4
        self.assertEqual(len(results), 3)
        
    def test_cleaner(self):
        log = remove_empty_folders(TEST_DIR, dry_run=False)
        # Should remove empty_dir and deep/empty and deep (if empty after child removed)
        self.assertFalse(os.path.exists(os.path.join(TEST_DIR, "empty_dir")))
        
    def test_renamer(self):
        # Rename file1.txt to file1_new.txt
        bulk_rename(TEST_DIR, "file1", "replacement", recursive=True, dry_run=False)
        # Should now be replacement.txt
        self.assertTrue(os.path.exists(os.path.join(TEST_DIR, "replacement.txt")))
        
    def test_integrity(self):
        snap = "snapshot.json"
        IntegrityMonitor.create_snapshot(TEST_DIR, snap)
        
        # Modify a file
        with open(os.path.join(TEST_DIR, "file3.jpg"), 'w') as f:
            f.write("modified content")
            
        issues = IntegrityMonitor.verify_snapshot(TEST_DIR, snap)["discrepancies"]
        self.assertTrue(any("MODIFIED" in i for i in issues))
        
        if os.path.exists(snap):
            os.remove(snap)

if __name__ == '__main__':
    unittest.main()
