# SPDX-License-Identifier: MIT

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ops import host_state


class HostStateTest(unittest.TestCase):
    def setUp(self):
        self.before = {"packages": {"base": ["ii", "1"]}}
        self.after = {"packages": {**self.before["packages"], "incus": ["hi", "7"], "fixture:amd64": ["ii", "1"]}}
        self.plan = "Inst incus (7)\nInst fixture (1)\n"

    def test_package_delta_preserves_baseline_and_requires_exact_purge(self):
        host_state.verify_install_plan(self.before, self.plan)
        self.assertEqual(host_state.additions(self.before, self.after, self.plan), ["fixture:amd64", "incus"])
        with patch.object(host_state, "packages", return_value=self.after["packages"]):
            host_state.verify_purge_plan(self.before, self.after, self.plan, "Purg incus\nPurg fixture")
            with self.assertRaisesRegex(SystemExit, "unexpected package"):
                host_state.verify_purge_plan(self.before, self.after, self.plan, "Purg incus\nPurg base")
        with self.assertRaisesRegex(SystemExit, "existing package"):
            host_state.verify_install_plan(self.before, "Inst base [1] (2)\n")
        self.assertEqual(host_state.additions(self.before, self.after, "Inst incus (7)\n"), ["incus"])

    def test_module_rollback_preserves_baseline_and_retries_by_dependency_order(self):
        active = {"kvm": 1, "vsock": 1, "vhost_vsock": 0}
        before = {"modules": ["kvm"]}
        after = {"modules": ["kvm", "vsock"]}
        removed = []

        def unload(_binary, _flag, name):
            removed.append(name)
            del active[name]
            if name == "vhost_vsock":
                active["vsock"] = 0

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            host_state, "modules", side_effect=lambda: active.copy(),
        ), patch.object(host_state, "run", side_effect=unload):
            evidence = Path(tmp) / "run"
            evidence.mkdir()
            (evidence / "modules").write_text("kvm\nvsock\nvhost_vsock\n")
            host_state.restore_modules(before, after, Path(tmp))
        self.assertEqual(removed, ["vhost_vsock", "vsock"])
        self.assertEqual(set(active), {"kvm"})


    def test_final_check_distinguishes_unrelated_changes_from_residue(self):
        before = {**self.before, "auto": [], "users": {}, "groups": {}, "subids": {}, "modules": ["kvm"]}
        installed = {**before, **self.after, "subids": {"subuid": {"text": "root:100000:1000"}}}
        reverted = {**before, "packages": {"base": ["ii", "2"], "other": ["ii", "1"]},
                    "subids": {"subuid": {"text": "unrelated:300000:1000"}}, "modules": ["kvm", "other"]}
        with patch("builtins.print") as report:
            host_state.compare(before, installed, reverted, self.plan, {"vsock"})
        report.assert_called_once()
        with self.assertRaisesRegex(SystemExit, "baseline package removed"):
            host_state.compare(before, installed, {**reverted, "packages": {}}, self.plan, {"vsock"})
        with self.assertRaisesRegex(SystemExit, "range still present"):
            host_state.compare(before, installed, {**reverted, "subids": installed["subids"]}, self.plan, {"vsock"})

    def test_ownership_scan_uses_local_mount_roots_and_explicit_prunes(self):
        def mount(target, fstype):
            return {"target": target, "fstype": fstype}
        mounts = [mount("/", "btrfs"), mount("/home", "btrfs"), mount("/media/network", "nfs"),
                  mount("/media/fuse", "fuse.sshfs"), mount("/.snapshots/past", "btrfs")]
        command = host_state.ownership_command(mounts, {123}, {456})
        self.assertEqual(command[7:10], ["/", "/home", "-xdev"])
        self.assertIn("/media/network", command[10:])
        self.assertIn("/media/fuse", command[10:])
        self.assertIn(".*-snapshots", command)
        self.assertNotIn("/.snapshots/past", command)
        self.assertEqual(host_state.SCAN_TIMEOUT, 90)


    def test_btrfs_subvolumes_map_to_mounted_tree_and_prune_snapshots(self):
        mount = {"target": "/", "fstype": "btrfs", "fsroot": "/fixture"}
        listing = ("ID 301 gen 20 top level 256 path fixture/home\n"
                   "ID 302 gen 21 top level 301 path fixture/home/admin\n"
                   "ID 303 gen 22 top level 256 path fixture/.snapshots/archive\n"
                   "ID 304 gen 20 top level 5 path <FS_TREE>/unmounted sibling\n")
        found = list(host_state.subvolume_targets(mount, listing))
        self.assertEqual(found, ["/home", "/home/admin", "/.snapshots/archive"])
        command = host_state.ownership_command([mount], {2}, set(), found)
        self.assertIn("/home/admin", command)
        self.assertNotIn("/.snapshots/archive", command)
