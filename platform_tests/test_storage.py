import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.v2.storage import FileStore


class StorageDurabilityTests(unittest.TestCase):
    def test_retry_repairs_incomplete_content_without_changing_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory))
            original = b"real source bytes\n" * 1000
            key, digest = store.put(original, "raw", ".csv")
            store.path(key).write_bytes(b"")
            self.assertEqual(store.put(original, "raw", ".csv"), (key, digest))
            self.assertEqual(store.verify(key, digest).read_bytes(), original)
            source = Path(directory) / "export.csv"
            source.write_bytes(original)
            store.path(key).write_bytes(b"partial")
            self.assertEqual(store.put_file(source, "raw", ".csv"), (key, digest))
            self.assertEqual(store.verify(key, digest).read_bytes(), original)

    def test_failed_disk_flush_never_publishes_a_file_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(Path(directory))
            original = b"immutable evidence"
            digest = hashlib.sha256(original).hexdigest()
            target = store.path(f"evidence/{digest[:2]}/{digest}.txt")
            with patch("app.v2.storage.os.fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    store.put(original, "evidence", ".txt")
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).rglob("*.tmp")), [])
            key, actual = store.put(original, "evidence", ".txt")
            self.assertEqual(store.verify(key, actual).read_bytes(), original)
