# SPDX-License-Identifier: MIT

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from ops.trust import remove_ci_paths, verify_runner


def populate_runner(root):
    entries = {".reviewed-commit": "a" * 40 + "\n", "ci/run": "runner", "ci/preflight.py": "preflight",
               "ops/trust.py": "trust", "ops/incus-host": "maintenance"}
    root.mkdir(exist_ok=True, parents=True)
    for name, text in entries.items():
        path = root / name
        path.parent.mkdir(mode=0o755, exist_ok=True)
        path.write_text(text)
        path.chmod(0o644)
    manifest = root / ".runner-sha256"
    manifest.write_text("".join(f"{hashlib.sha256(text.encode()).hexdigest()}  {name}\n"
                                for name, text in entries.items()))
    manifest.chmod(0o644)


class RunnerTrustTest(unittest.TestCase):
    def test_manifest_modes_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            populate_runner(root)
            verify_runner(root, uid=os.getuid())
            entry = root / "ci/run"
            entry.write_text("tampered")
            with self.assertRaisesRegex(SystemExit, "checksum mismatch"):
                verify_runner(root, uid=os.getuid())
            entry.write_text("runner")
            entry.chmod(0o666)
            with self.assertRaisesRegex(SystemExit, "Untrusted"):
                verify_runner(root, uid=os.getuid())

    def test_cleanup_is_idempotent_and_stops_before_removing_unknown_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner = Path(tmp) / "opt" / "runner"
            anchors = Path(tmp) / "etc"
            populate_runner(runner)
            anchors.mkdir(mode=0o700)
            (anchors / "release.allowed_signers").touch(mode=0o600)
            extra = anchors / "other"
            extra.touch(mode=0o600)
            with self.assertRaisesRegex(SystemExit, "Unexpected CI trust entries"):
                remove_ci_paths(runner, anchors, uid=os.getuid())
            self.assertTrue(runner.is_dir())
            self.assertTrue(extra.exists())
            extra.unlink()
            remove_ci_paths(runner, anchors, uid=os.getuid())
            remove_ci_paths(runner, anchors, uid=os.getuid())
            self.assertFalse(runner.parent.exists())
            self.assertFalse(anchors.exists())
