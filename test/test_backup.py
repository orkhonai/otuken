# SPDX-License-Identifier: MIT

import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import backup


class BtrfsBackupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="otuken-btrfs-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "config-parent" / "config"
        self.data = self.root / "data-parent" / "data"
        self.paths = SimpleNamespace(config=self.config, data=self.data, fs="btrfs")
        for name in (self.config, self.data):
            name.parent.mkdir()
        self.native = shutil.which("btrfs") is not None and subprocess.run(
            ["btrfs", "subvolume", "create", self.config], capture_output=True, check=False,
        ).returncode == 0
        if self.native:
            subprocess.run(["btrfs", "subvolume", "create", self.data], check=True, capture_output=True)
        else:
            self.config.mkdir()
            self.data.mkdir()
        (self.data / "backups").mkdir()
        self.addCleanup(self.unlock_snapshots)

    def unlock_snapshots(self):
        if self.native:
            for path in (self.data / "backups").glob("*/*"):
                if path.is_dir() and path.stat().st_ino == 256:
                    subprocess.run(["btrfs", "property", "set", "-ts", path, "ro", "false"],
                                   check=True, capture_output=True)

    def checkpoint(self):
        if self.native:
            return backup.create(self.paths, 1)
        identifier = uuid.uuid4().hex
        target = self.data / "backups" / identifier
        target.mkdir()
        shutil.copytree(self.config, target / "config")
        shutil.copytree(self.data, target / "data", ignore=shutil.ignore_patterns("backups"))
        return identifier

    def test_btrfs_restore_replaces_paths_inside_target_subvolumes(self):
        (self.config / "policy").mkdir()
        (self.config / "policy/choice").write_text("before")
        (self.config / "link").symlink_to("policy/choice")
        (self.data / "state").mkdir()
        (self.data / "state/value").write_text("before")
        (self.data / "vault").mkdir()
        (self.data / "vault/page").write_text("previous page")
        identifier = self.checkpoint()
        (self.config / "policy/choice").write_text("partial change")
        (self.config / "link").unlink()
        (self.config / "link").write_text("ordinary file")
        (self.config / "extra").touch()
        (self.data / "vault/page").write_text("current page")
        actual = backup.exchange

        def same_subvolume(source, destination):
            self.assertEqual(os.stat(source.parent).st_dev, os.stat(destination.parent).st_dev)
            self.assertEqual(source.parent.parent, destination.parent)
            actual(source, destination)

        with patch.object(backup, "exchange", same_subvolume):
            backup.restore(self.paths, identifier)
            backup.restore(self.paths, identifier)
        if self.native:
            self.assertNotEqual(self.config.stat().st_dev, self.config.parent.stat().st_dev)
            self.assertEqual(self.config.stat().st_ino, 256)
        self.assertEqual((self.config / "policy/choice").read_text(), "before")
        self.assertEqual(os.readlink(self.config / "link"), "policy/choice")
        self.assertEqual((self.data / "vault/page").read_text(), "current page")
        self.assertFalse((self.config / "extra").exists())
        self.assertFalse((self.config / backup.RESTORE_STAGE).exists())
        self.assertFalse((self.data / backup.RESTORE_STAGE).exists())

    def test_final_export_is_outside_data_without_credentials(self):
        (self.data / "credentials").mkdir()
        (self.data / "credentials/key").write_text("fixture")
        (self.config / "owner").write_text("choice")
        identifier = uuid.uuid4().hex
        kept = backup.final_export(self.paths, identifier, 1)
        self.assertEqual(kept, self.data.parent / f"otuken-purge-{identifier}")
        self.assertEqual(backup.final_export(self.paths, identifier, 1), kept)
        with tarfile.open(kept / "data.tar") as archive:
            self.assertEqual(archive.getnames(), [])
        with tarfile.open(kept / "config.tar") as archive:
            self.assertEqual(archive.getnames(), ["owner"])

    def test_interrupted_legacy_purge_scrubs_already_exported_credentials(self):
        (self.data / "credentials").mkdir()
        (self.data / "credentials/key").write_text("legacy fixture")
        (self.data / "vault").mkdir()
        (self.data / "vault/page").write_text("to retain")
        identifier = uuid.uuid4().hex
        kept = self.data.parent / f"otuken-purge-{identifier}"
        kept.mkdir(mode=0o700)
        backup.export(self.config, kept / "config.tar", set())
        backup.export(self.data, kept / "data.tar", {"backups"})
        backup.final_export(self.paths, identifier, 1, legacy=True)
        with tarfile.open(kept / "data.tar") as archive:
            self.assertEqual(archive.getnames(), ["vault", "vault/page"])
            self.assertEqual(archive.extractfile("vault/page").read(), b"to retain")

    def test_pruning_keeps_the_rollback_target_and_three_recent(self):
        paths = SimpleNamespace(data=self.data, fs="export")
        ids = [uuid.uuid4().hex for _ in range(6)]
        for order, identifier in enumerate(ids):
            child = self.data / "backups" / identifier
            child.mkdir()
            os.utime(child, (order + 1, order + 1))
        backup.prune(paths, [ids[0]])
        self.assertEqual({path.name for path in (self.data / "backups").iterdir()}, {ids[0], *ids[-3:]})
