# SPDX-License-Identifier: MIT

import hashlib
import io
import json
import os
import signal
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signing = tempfile.TemporaryDirectory()
        cls.key = Path(cls.signing.name) / "release"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", cls.key], check=True)
        cls.signers = cls.key.with_name("allowed_signers")
        cls.signers.write_text("otuken-release " + cls.key.with_suffix(".pub").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.signing.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / "host"
        self.root.mkdir()
        (self.root / "run").mkdir()
        self.config = self.root / "etc/otuken"
        self.state = self.root / "var/lib/otuken"

    def sign(self, path, namespace, key=None):
        subprocess.run(["ssh-keygen", "-Y", "sign", "-f", key or self.key, "-n", namespace, path],
                       check=True, capture_output=True)

    def bundle(self, version, *, migration=None, unsafe=False, expires="2099-01-01T00:00:00Z",
               channel="stable", key=None, signers=None):
        folder = self.parent / version
        folder.mkdir()
        archive = folder / f"otuken-{version}.tar.gz"
        runtime = ("otuken", "version", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md",
                   "docs/THIRD-PARTY-TOOLS.md", "bin/otuken", "bin/otukenctl",
                   "install/systemd/otuken-guard-request.service",
                   "default/guard-policy.json", "default/installer.json",
                   *(str(p.relative_to(ROOT)) for p in (ROOT / "engine").glob("*.py")))
        with tarfile.open(archive, "w:gz") as output:
            for name, data in [
                *((name, version.encode() if name == "version" else (ROOT / name).read_bytes())
                  for name in runtime),
                *([("migrations/1780000000.py", migration.encode())] if migration else []),
            ]:
                member = tarfile.TarInfo(f"otuken-{version}/{name}")
                member.size = len(data)
                output.addfile(member, io.BytesIO(data))
            if unsafe:
                member = tarfile.TarInfo(f"otuken-{version}/unsafe")
                member.type = tarfile.SYMTYPE
                member.linkname = "/"
                output.addfile(member)
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        sums = folder / "SHA256SUMS"
        sums.write_text(f"{checksum}  {archive.name}\n")
        self.sign(sums, "otuken-release", key)
        metadata = folder / (channel + ".json")
        metadata.write_text(json.dumps({"channel": channel, "version": version,
                                        "sha256": checksum, "expires": expires}))
        self.sign(metadata, "otuken-channel", key)
        return ("--bundle", folder, "--version", version, "--allowed-signers", signers or self.signers)

    def cli(self, *args, code=0, command=ROOT / "otuken"):
        result = subprocess.run([command, "--root", self.root, *args], capture_output=True, text=True, check=False,
                                env={**os.environ, "LC_ALL": "C.UTF-8"})
        self.assertEqual(result.returncode, code, result.stderr + result.stdout[-1400:])
        return result

    def plan(self, *args, code=2):
        return json.loads(self.cli(*args, "--json", code=code).stdout)

    def apply(self, operation, *params):
        plan = self.plan(operation, *params)
        self.cli(operation, *params, "--plan-digest", plan["digest"])

    def test_signature_tampering_and_unsafe_members(self):
        params = self.bundle("1.0.0")
        self.cli("verify", *params)
        archive = params[1] / "otuken-1.0.0.tar.gz"
        with archive.open("ab") as stream:
            stream.write(b"altered")
        self.assertIn("checksum mismatch", self.cli("verify", *params, code=1).stderr)
        params = self.bundle("1.0.1", unsafe=True)
        self.assertIn("member type", self.cli("verify", *params, code=1).stderr)
        (params[1] / "SHA256SUMS").write_text("altered")
        self.assertIn("Invalid SSH signature", self.cli("verify", *params, code=1).stderr)

    def test_plan_digest_binds_overlay_and_second_apply_is_empty(self):
        params = self.bundle("1.0.0")
        overlay = self.parent / "overlay"
        overlay.mkdir()
        source = overlay / "installer.json"
        source.write_text('{"snapshot_free_percent": 20}')
        first = self.plan("plan", *params, "--overlay", overlay)
        self.assertFalse(self.config.exists())
        source.write_text('{"snapshot_free_percent": 21}')
        mismatched = self.cli("apply", *params, "--overlay", overlay,
                              "--plan-digest", first["digest"], code=1)
        self.assertIn("Plan changed", mismatched.stderr)
        self.assertFalse(self.config.exists())
        second = self.plan("install", *params, "--overlay", overlay)
        self.cli("install", *params, "--overlay", overlay, "--apply", "--plan-id", second["digest"])
        self.assertEqual((self.config / "overlay/installer.json").read_text(), source.read_text())
        launcher = self.root / "opt/otuken/current/otuken"
        before = launcher.stat().st_mtime_ns
        empty = self.plan("plan", *params, code=0)
        self.assertEqual(empty["plan"]["changes"], [])
        self.assertIn("No changes", self.cli("apply", *params, "--plan-digest", empty["digest"]).stdout)
        self.assertEqual(launcher.stat().st_mtime_ns, before)
        self.assertEqual(json.loads(self.cli("status", command=launcher).stdout)["current"], "1.0.0")
        bin_launcher = self.root / "opt/otuken/current/bin/otuken"
        ctl_launcher = self.root / "opt/otuken/current/bin/otukenctl"
        self.assertEqual(json.loads(self.cli("status", command=bin_launcher).stdout)["current"], "1.0.0")
        self.assertEqual(json.loads(self.cli("status", command=ctl_launcher).stdout)["current"], "1.0.0")

    def test_upgrade_rollback_and_owned_uninstall(self):
        previous = self.bundle("1.0.0")
        self.apply("install", *previous)
        (self.config / "owner.json").write_text("before")
        (self.state / "state/work").write_text("before")
        (self.state / "vault/page").write_text("initial")
        (self.state / "projects/project-a").write_text("unpublished fixture")
        unrelated = self.root / "opt/unrelated"
        unrelated.write_text("keep")
        candidate = self.bundle(
            "1.1.0", migration="from pathlib import Path\nimport sys\n"
            "(Path(sys.argv[1]) / 'owner.json').write_text('migrated')\n"
            "(Path(sys.argv[2]) / 'state/work').write_text('migrated')\n",
        )
        self.apply("update", *candidate)
        self.assertEqual((self.config / "owner.json").read_text(), "migrated")
        self.assertTrue((self.state / "state/migrations/1780000000").is_file())
        self.assertEqual(self.cli("migrations", "--pending").stdout, "")
        (self.state / "vault/page").write_text("current")
        self.apply("rollback")
        self.assertEqual((self.config / "owner.json").read_text(), "before")
        self.assertEqual((self.state / "state/work").read_text(), "before")
        self.assertFalse((self.state / "state/migrations/1780000000").exists())
        self.assertEqual((self.state / "vault/page").read_text(), "current")
        self.assertIn("highest", self.cli("update", *previous, code=1).stderr)
        self.assertIn("Project data", self.cli("uninstall", "--purge", code=1).stderr)
        self.apply("uninstall")
        self.assertFalse((self.root / "opt/otuken").exists())
        self.assertTrue(unrelated.exists())
        self.assertEqual((self.state / "projects/project-a").read_text(), "unpublished fixture")
        self.plan("uninstall", code=0)

    def test_failed_migration_restores_previous_without_losing_work(self):
        self.apply("install", *self.bundle("1.0.0"))
        (self.config / "owner.json").write_text("before")
        candidate = self.bundle("1.1.0", migration="from pathlib import Path\nimport sys\n"
                                "(Path(sys.argv[1]) / 'owner.json').write_text('partial')\n"
                                "raise SystemExit(3)\n")
        plan = self.plan("update", *candidate)
        self.cli("update", *candidate, "--plan-digest", plan["digest"], code=1)
        self.assertEqual((self.config / "owner.json").read_text(), "before")
        status = json.loads(self.cli("status").stdout)
        self.assertEqual(status["current"], "1.0.0")
        self.assertFalse(status["recovery_pending"])
        self.assertEqual(self.plan("update", *candidate)["plan"]["current"], "1.0.0")

    def test_recover_after_interrupted_update(self):
        self.apply("install", *self.bundle("1.0.0"))
        marker = self.config / "migration-started"
        candidate = self.bundle(
            "1.1.0", migration="from pathlib import Path\nimport sys, time\n"
            "(Path(sys.argv[1]) / 'migration-started').touch()\n"
            "time.sleep(30)\n",
        )
        plan = self.plan("update", *candidate)
        command = [ROOT / "otuken", "--root", self.root, "update", *candidate,
                   "--plan-digest", plan["digest"]]
        with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True) as process:
            try:
                deadline = time.monotonic() + 5
                while not marker.is_file() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.025)
                self.assertTrue(marker.is_file(), "Migration did not reach its interruption point")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
        self.assertTrue(json.loads(self.cli("status").stdout)["recovery_pending"])
        self.cli("recover")
        self.assertFalse(marker.exists())
        self.assertFalse(json.loads(self.cli("status").stdout)["recovery_pending"])
        self.assertEqual(self.plan("update", *candidate)["plan"]["current"], "1.0.0")

    def test_expiry_and_unsigned_overlay(self):
        self.apply("install", *self.bundle("1.0.0"))
        candidate = self.bundle("1.1.0", expires="2000-01-01T00:00:00Z")
        self.assertIn("expired", self.cli("update", *candidate, code=1).stderr)
        (self.config / "overlay/installer.json").symlink_to("/dev/null")
        self.assertIn("Unsafe file", self.cli("plan", *candidate, code=1).stderr)

    def test_purge_requires_typed_confirmation_and_keeps_final_checkpoint(self):
        self.apply("install", *self.bundle("1.0.0"))
        (self.config / "owner.json").write_text("keep in checkpoint")
        (self.state / "vault/page").write_text("vault checkpoint")
        (self.state / "credentials/test").write_text("fixture credential")
        plan = self.plan("uninstall", "--purge")
        args = ("uninstall", "--purge", "--plan-digest", plan["digest"])
        self.cli(*args, code=1)
        self.assertTrue(self.config.exists())
        self.cli(*args, "--confirm", "purge otuken")
        self.assertFalse(self.config.exists())
        self.assertFalse(self.state.exists())
        kept, = self.state.parent.glob("otuken-purge-*")
        with tarfile.open(kept / "config.tar") as checkpoint:
            self.assertIn("owner.json", checkpoint.getnames())
        with tarfile.open(kept / "data.tar") as checkpoint:
            self.assertIn("vault/page", checkpoint.getnames())
            self.assertFalse(any(name.startswith("credentials") for name in checkpoint.getnames()))


    def test_install_pins_signer_and_rotation_requires_out_of_band_fingerprint(self):
        original = self.bundle("1.0.0")
        installed_plan = self.plan("install", *original)
        self.assertTrue(installed_plan["plan"]["signer"].startswith("SHA256:"))
        self.apply("install", *original)
        key = self.parent / "alternate"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
        pub = key.with_suffix(".pub")
        signers = self.parent / "other-signers"
        signers.write_text("otuken-release " + pub.read_text())
        candidate = self.bundle("1.1.0", key=key, signers=signers)
        for command in ("update", "verify"):
            self.assertIn("installed pin", self.cli(command, *candidate, code=1).stderr)
            self.assertIn("Invalid SSH signature", self.cli(command, *candidate[:-2], code=1).stderr)
        self.cli("rotate-key", "--allowed-signers", signers, "--fingerprint", "SHA256:invalid", code=1)
        fingerprint = subprocess.check_output(["ssh-keygen", "-lf", pub], text=True).split()[1]
        self.cli("rotate-key", "--allowed-signers", signers, "--fingerprint", fingerprint)
        receipt, = (self.state / "control/release-key-rotations").glob("*.json")
        event = json.loads(receipt.read_text())
        self.assertEqual(event["state"], "installed")
        self.assertEqual(event["next"], fingerprint)
        self.assertEqual(event["previous"], installed_plan["plan"]["signer"])
        self.apply("update", *candidate[:-2])
        self.apply("rollback")
        self.assertEqual((self.state / "control/release-signers").stat().st_mode & 0o777, 0o600)
        self.assertIn(fingerprint, self.cli("verify", *candidate[:-2]).stdout)
        self.assertIn("installed pin", self.cli("verify", *original, code=1).stderr)

    def test_reinstall_migrates_retained_data_behind_an_export(self):
        self.apply("install", *self.bundle("1.0.0"))
        (self.state / "state/work").write_text("v1-format")
        self.apply("uninstall")
        self.assertFalse((self.root / "opt/otuken/current").exists())
        successor = self.bundle("1.1.0", migration=(
            "from pathlib import Path\nimport sys\n"
            "state = Path(sys.argv[2])\n"
            "assert any((state / 'backups').glob('*/data.tar'))\n"
            "work = state / 'state/work'\n"
            "assert work.read_text() == 'v1-format'\n"
            "work.write_text('v2-format')\n"
        ))
        actions = [row["action"] for row in self.plan("install", *successor)["plan"]["changes"]]
        self.assertLess(actions.index("export"), actions.index("migrate"))
        self.assertNotIn("mark-baseline", actions)
        self.apply("install", *successor)
        self.assertEqual((self.state / "state/work").read_text(), "v2-format")
        self.assertEqual((self.state / "state/migrations/1780000000").read_text(), "applied\n")

    def test_fresh_install_marks_migrations_without_running_them(self):
        release = self.bundle("1.0.0", migration="raise SystemExit(42)\n")
        plan = self.plan("install", *release)
        self.assertIn("mark-baseline", {item["action"] for item in plan["plan"]["changes"]})
        self.apply("install", *release)
        marker = self.state / "state/migrations/1780000000"
        self.assertEqual(marker.read_text(), "baseline\n")
        self.assertEqual(self.cli("migrations", "--pending").stdout, "")

    def test_recovery_cleans_old_ext4_staging(self):
        self.apply("install", *self.bundle("1.0.0"))
        old = self.state.parent / ".otuken-restore-abcd1234"
        old.mkdir(mode=0o700)
        (old / "fixture").write_text("old restore")
        self.cli("recover")
        self.assertFalse(old.exists())

    def test_repository_version_is_valid_prealpha_release(self):
        import release
        from ci.stage import VERSION as STAGE_VERSION

        repo_version = (ROOT / "version").read_text().strip()
        key = release.version_key(repo_version)
        self.assertFalse(key[3])  # prerelease
        self.assertLess(key, release.version_key("0.1.0"))
        self.assertIsNotNone(STAGE_VERSION.fullmatch(repo_version))
        self.apply("install", *self.bundle("0.0.1-prealpha.0", channel="rc"))
        bundle = self.bundle(repo_version, channel="rc")
        folder = bundle[1]
        rc_meta = json.loads((folder / "rc.json").read_text())
        stable_meta = folder / "stable.json"
        stable_meta.write_text(json.dumps({**rc_meta, "channel": "stable"}))
        self.sign(stable_meta, "otuken-channel")
        self.cli("update", "--plan", "--channel", "stable", *bundle[:-2], code=1)
        self.apply("update", "--channel", "rc", *bundle[:-2])
        status = json.loads(self.cli("status").stdout)
        self.assertEqual(status["current"], repo_version)


if __name__ == "__main__":
    unittest.main()
