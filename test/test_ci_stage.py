# SPDX-License-Identifier: MIT

import os
import tempfile
import unittest
from pathlib import Path

from ci.stage import copy


class FixtureCopyTest(unittest.TestCase):
    def test_stages_snapshot_from_regular_file_and_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture"
            fixture.write_bytes(b"fixture")
            target = root / "staged"
            fd = os.open(root, os.O_DIRECTORY)
            try:
                copy(fd, "fixture", target, 16)
                fixture.write_bytes(b"changed")
                self.assertEqual(target.read_bytes(), b"fixture")
                (root / "alias").symlink_to(fixture)
                with self.assertRaises(OSError):
                    copy(fd, "alias", root / "invalid", 16)
                with self.assertRaisesRegex(SystemExit, "Invalid staged fixture"):
                    copy(fd, "fixture", root / "oversized", 2)
            finally:
                os.close(fd)
