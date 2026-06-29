from pathlib import Path
import tempfile
import unittest
from ai_harness.errors import LockError
from ai_harness.stores.runtime import RunLock


class RuntimeLockTests(unittest.TestCase):
    def test_concurrent_lock_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = RunLock(Path(directory)), RunLock(Path(directory))
            with first:
                with self.assertRaises(LockError): second.acquire()
            with second: pass
