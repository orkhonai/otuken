# SPDX-License-Identifier: MIT

import io
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import breakglass
from common import Error


class BreakGlassTest(unittest.TestCase):
    def test_drift_is_path_attributed_and_package_baselines_are_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = SimpleNamespace(root=root, code=root / "opt/otuken",
                                    config=root / "etc/otuken", data=root / "var/lib/otuken",
                                    control=root / "var/lib/otuken/control", fs="ext4")
            home = root / "home/owner"
            (paths.data / "backups").mkdir(parents=True)
            files = [
                paths.code / "current", paths.config / "guard-policy.json", paths.control / "release-signers",
                paths.data / "journal/guard", paths.data / "credentials/key",
                root / "etc/ld.so.preload", root / "etc/pam.d/fixture", root / "etc/profile.d/fixture",
                root / "etc/apt/apt.conf.d/fixture", root / "var/spool/cron/crontabs/fixture",
                root / "usr/local/bin/fixture", root / "etc/systemd/system/test.service",
                root / "etc/sudoers.d/fixture", root / "etc/passwd", home / ".ssh/authorized_keys",
                paths.data / "backups/one/data.tar",
            ]
            for path in files:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("baseline")
            with patch.object(breakglass, "package_verification", side_effect=[
                {"/usr/bin/known": "old"}, {"/usr/bin/known": "old", "/usr/bin/drifted": "new"},
            ]):
                before = breakglass.snapshot(paths, [home], "guard-test.service")
                for path in files:
                    path.write_text("changed")
                after = breakglass.snapshot(paths, [home], "guard-test.service")
            declared = [str(root / "etc/pam.d") + "/", str(root / "etc/ld.so.preload")]
            report = breakglass.drift(before, after, declared)
            self.assertEqual({entry["path"] for entry in report["declared"]},
                             {str(files[5]), str(files[6])})
            self.assertEqual({entry["path"] for entry in report["unexpected"]},
                             ({str(path) for path in files} - {str(files[5]), str(files[6])}) | {"/usr/bin/drifted"})
            self.assertFalse(report["unavailable"])

    def test_new_persistence_files_and_off_window_changes_are_classified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home/admin"
            paths = SimpleNamespace(root=root, code=root / "opt/otuken",
                                    data=root / "var/lib/otuken", control=root / "control", fs="ext4")
            (paths.data / "backups").mkdir(parents=True)
            concurrent = root / "etc" / "fixture"
            concurrent.parent.mkdir()
            concurrent.write_text("old")
            existing = root / "usr/lib/unowned module.py"
            existing.parent.mkdir(parents=True)
            existing.write_text("old")
            paths_to_add = [
                root / "usr/lib/python3/dist-packages/fixture.pth",
                root / "usr/lib/udev/rules.d/fixture.rules",
                home / ".config/systemd/user/fixture.service",
                root / "root/.bashrc",
                root / "usr/bin/unowned",
            ]

            def verify(_timeout):
                concurrent.write_text("concurrently changed")
                return {}

            with patch.object(breakglass, "package_verification", side_effect=verify):
                before = breakglass.snapshot(paths, [home, root / "root"], "repair.service", edge="before")
                for path in paths_to_add:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("fixture")
                existing.write_text("new")
                after = breakglass.snapshot(paths, [home, root / "root"], "repair.service", edge="after")
            report = breakglass.drift(before, after, [])
            self.assertEqual(report["concurrent"], [str(concurrent)])
            self.assertTrue({str(path) for path in paths_to_add}
                            <= {row["path"] for row in report["unexpected"]})
            self.assertIn({"source": "usr-inventory", "path": str(existing), "change": "changed"},
                          report["unexpected"])
            self.assertNotIn(str(concurrent), {row["path"] for row in report["unexpected"]})

    def test_root_service_keeps_cgroup_limits_without_a_sandbox(self):
        command = breakglass.transient_command("a" * 64)
        for value in ("--wait", "--uid=0", "--property=KillMode=control-group",
                      "--property=ExitType=main", "--property=RuntimeMaxSec=120s"):
            self.assertIn(value, command)
        for setting in ("SystemCallFilter", "CapabilityBoundingSet", "LimitFSIZE", "ProtectSystem"):
            self.assertFalse(any(setting in arg for arg in command))

    def test_output_cap_keeps_draining_the_pipe(self):
        reader, writer = os.pipe()
        with os.fdopen(reader, "rb") as source, os.fdopen(writer, "wb") as sink:
            sink.write(b"12345678")
            sink.close()
            output = io.BytesIO()
            self.assertTrue(breakglass.capture_output(source, output, time.monotonic() + 1, limit=4))
            self.assertEqual(output.getvalue(), b"1234")

    def test_bounded_runner_checks_that_cgroup_stopped(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            breakglass, "transient_command", return_value=["/bin/cat"],
        ), patch.object(breakglass, "SYSTEMCTL", "/bin/true"), patch.object(
            breakglass, "cgroup_empty", return_value=False,
        ), self.assertRaisesRegex(Error, "cgroup still has processes"):
            breakglass.execute("a" * 64, "approved text", Path(tmp) / "script.log")

    def test_verify_uses_package_names_and_paths_in_drift(self):
        result = subprocess.CompletedProcess([], 0, b"??5?????? c /etc/example\nmissing /usr/bin/example\n", b"")
        with patch.object(breakglass.subprocess, "run", return_value=result) as run:
            self.assertEqual(set(breakglass.package_verification()), {"/etc/example", "/usr/bin/example"})
            self.assertIn("--verify", run.call_args.args[0])

    def test_typed_request_sandbox_blocks_dac_read_search_and_io_uring(self):
        unit = Path(__file__).resolve().parents[1] / "install/systemd/otuken-guard-request.service"
        text = unit.read_text()
        self.assertIn("CapabilityBoundingSet=~CAP_DAC_READ_SEARCH", text)
        self.assertIn("SystemCallFilter=~io_uring_setup io_uring_enter io_uring_register", text)
