# SPDX-License-Identifier: MIT

import gzip
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci import isolation
from ci.fixture import initramfs, provenance, topology
from ops import ci_residue, first_run_health, first_run_inputs, fixture_manifest

SCANNER = Path(initramfs.__file__).with_name("manifest-guest.py")
spec = importlib.util.spec_from_file_location("fixture_guest_scanner", SCANNER)
guest_scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest_scanner)


def qcow(external=False):
    header = bytearray(104)
    struct.pack_into(">4sIQIIQI", header, 0, b"QFI\xfb", 3, 0, 0, 16, 8 * 1024**3, 0)
    struct.pack_into(">Q", header, 72, 4 if external else 0)
    return bytes(header)


class FirstRunTest(unittest.TestCase):
    def test_ubuntu_requires_pinned_signer_and_unique_image_entry(self):
        key = first_run_inputs.UBUNTU_KEY
        marker = f"[GNUPG:] VALIDSIG {key} 2026-08-01 123 0 4 0 1 10 00 {key}\n"
        row = "a" * 64 + " *" + first_run_inputs.UBUNTU_IMAGE
        self.assertEqual(first_run_inputs.signed_checksum(marker, row, first_run_inputs.UBUNTU_IMAGE), "a" * 64)
        with self.assertRaisesRegex(SystemExit, "pinned"):
            first_run_inputs.signed_checksum(marker.replace(key, "0" * 40), row, first_run_inputs.UBUNTU_IMAGE)
        with self.assertRaisesRegex(SystemExit, "exactly one"):
            first_run_inputs.signed_checksum(marker, row + "\n" + row, first_run_inputs.UBUNTU_IMAGE)

    @staticmethod
    def inventory(role, **files):
        directory = {"type": "directory", "mode": 0o755, "uid": 0, "gid": 0, "size": 0,
                     "sha256": hashlib.sha256(b"").hexdigest(), "xattrs": {}}
        sections = {name: {"/": directory.copy()} for name in fixture_manifest.PARTITIONS[role]}
        sections["root"].update(files)
        return {"schema": 1, "role": role, "packages": {"base:amd64": "1.0"}, "partitions": sections}

    def test_provenance_binds_verified_comparison_and_cold_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            evidence_dir = folder / "evidence"
            evidence_dir.mkdir()
            upstream = {"sha256": "a" * 64}
            commit = "c" * 40
            builder = {"account": "otuken-ci-build", "uid": 123}
            packs = {kind: {f"{kind}-{i:03}.deb": "d" * 64 for i in range(count)}
                     for kind, count in first_run_inputs.PACKAGE_COUNTS.items()}
            manifest = {
                kind: hashlib.sha256("".join(f"{sha}  {name}\n" for name, sha in entries.items()).encode()).hexdigest()
                for kind, entries in packs.items()
            }
            trusted = {}
            for role in fixture_manifest.ROLES:
                payload = gzip.compress(json.dumps(self.inventory(role)).encode(), mtime=0)
                trusted[role] = hashlib.sha256(payload).hexdigest()
                for origin in ("agent", "cold"):
                    (evidence_dir / f"{origin}.{role}.json.gz").write_bytes(payload)
            reviewed = {"manifests": trusted, "package_manifest_sha256": manifest, "ubuntu": upstream,
                        "sha256": "b" * 64, "recipe_sha256": "e" * 64}
            filesystem = fixture_manifest.evidence(first_run_inputs.manifest_paths(evidence_dir, "agent."),
                                                   first_run_inputs.manifest_paths(evidence_dir, "cold."), trusted)
            record = {
                "schema": 4, "ubuntu": upstream, "images": {}, "filesystem": filesystem,
                "build": {"commit": commit, "recipe_sha256": "e" * 64, "packages": packs,
                          "builder": builder, "reference_sha256": reviewed["sha256"]},
                "isolation": {"status": "passed", "log_sha256": "b" * 64,
                              "boot_sha256": {log: "b" * 64 for log in provenance.BOOT_LOGS}},
                "isolation_setup": "/opt/ci-fixture/isolation-setup",
            }
            for name in first_run_inputs.FILES:
                path = folder / name
                path.write_bytes(qcow() if name.endswith(".qcow2") else b"metadata")
                record["images"][name] = first_run_inputs.digest(path)
            proof = folder / "PROVENANCE.json"

            def verify(expected=None, expected_builder=builder):
                proof.write_text(json.dumps(record))
                return first_run_inputs.approved_inputs(folder, expected or first_run_inputs.digest(proof),
                                                       upstream, commit, reviewed, expected_builder)

            self.assertEqual(verify(), record["images"])
            with self.assertRaisesRegex(SystemExit, "provenance SHA"):
                verify("f" * 64)
            with self.assertRaisesRegex(SystemExit, "reviewed commit"):
                verify(expected_builder={"account": "build-user", "uid": 1001})
            packs["tool"]["tool-000.deb"] = "a" * 64
            with self.assertRaisesRegex(SystemExit, "tool package evidence differs"):
                verify()
            packs["tool"]["tool-000.deb"] = "d" * 64
            cold = self.inventory("ext4")
            cold["packages"]["base:amd64"] = "2.0"
            changed = evidence_dir / "cold.ext4.json.gz"
            old = changed.read_bytes()
            changed.write_bytes(gzip.compress(json.dumps(cold).encode(), mtime=0))
            with self.assertRaisesRegex(SystemExit, "installed package"):
                verify()
            changed.write_bytes(old)
            disk = folder / "ext4.disk.qcow2"
            disk.write_bytes(qcow(external=True))
            with self.assertRaisesRegex(SystemExit, "Cold media bytes"):
                verify()
            record["images"][disk.name] = first_run_inputs.digest(disk)
            with self.assertRaisesRegex(SystemExit, "external data"):
                verify()

    def test_manifest_exceptions_are_path_and_metadata_scoped(self):
        file = {"type": "file", "mode": 0o644, "uid": 0, "gid": 0, "size": 4, "sha256": "a" * 64, "xattrs": {}}
        symlink = {**file, "type": "symlink", "mode": 0o777}
        reference = self.inventory("ext4", **{
            "/etc/fstab": {**file, "uuid_normalized_sha256": "c" * 64},
            "/var/log/syslog": file, "/var/log/link": symlink,
            "/etc/systemd/service": file, "/etc/machine-id": file,
        })
        cold = self.inventory("ext4", **{
            "/etc/fstab": {**file, "sha256": "e" * 64, "uuid_normalized_sha256": "c" * 64},
            "/var/log/syslog": {**file, "sha256": "b" * 64},
            "/var/log/link": {**symlink, "sha256": "b" * 64},
            "/var/log/injected": {**file, "mode": 0o755},
            "/etc/systemd/service": {**file, "sha256": "b" * 64},
            "/etc/machine-id": {**file, "uid": 7},
        })
        rejected, allowed = fixture_manifest.compare("ext4", reference, cold, fixture_manifest.allowlist())
        self.assertEqual(dict(allowed), {"ext4:root:/etc/fstab": 1, "ext4:root:/var/log": 1})
        for path in ("/etc/machine-id", "/etc/systemd/service", "/var/log/link", "/var/log/injected"):
            self.assertIn(f"ext4 root {path!a}", rejected)
        cold["partitions"]["root"]["/etc/fstab"]["uuid_normalized_sha256"] = "f" * 64
        self.assertIn("ext4 root '/etc/fstab'",
                      fixture_manifest.compare("ext4", reference, cold, fixture_manifest.allowlist())[0])

    def test_comparison_refuses_media_changed_after_its_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "media").mkdir()
            (work / "manifests").mkdir()
            for name in first_run_inputs.FILES:
                (work / "media" / name).write_bytes(b"original")
            hashes = first_run_inputs.media_hashes(work / "media")
            (work / "manifests/images.sha256").write_text(
                "".join(f"{sha}  {name}\n" for name, sha in hashes.items()))
            self.assertEqual(first_run_inputs.check_inventoried_media(work), hashes)
            (work / "media/ext4.disk.qcow2").write_bytes(b"updated")
            with self.assertRaisesRegex(SystemExit, "Media changed since guest inventory"):
                first_run_inputs.check_inventoried_media(work)

    def test_scrubbed_paths_are_outside_the_allowlist(self):
        agent = self.inventory("ext4")
        directory = agent["partitions"]["root"]["/"]
        file = {**directory, "type": "file", "mode": 0o644, "size": 100}
        cold = self.inventory("ext4", **{path: file for path in guest_scanner.SCRUBBED}, **{
            "/var/log/journal/host/system.journal": file,
        })
        errors, allowed = fixture_manifest.compare("ext4", agent, cold, fixture_manifest.allowlist())
        self.assertFalse(allowed)
        self.assertEqual(len(errors), len(guest_scanner.SCRUBBED) + 1)

    def test_inventory_rejects_pending_ext4_journal_even_with_clean_state(self):
        clean = "Filesystem features: has_journal extent\nFilesystem state: clean\n"
        with patch.object(subprocess, "check_output", return_value=clean) as output:
            guest_scanner.require_clean("/dev/test", "ext4")
            output.assert_called_once_with(["dumpe2fs", "-h", "/dev/test"], text=True)
            output.return_value = clean.replace("extent", "extent needs_recovery")
            with self.assertRaisesRegex(SystemExit, "needs journal replay"):
                guest_scanner.require_clean("/dev/test", "ext4")

    def test_inventory_rejects_pending_btrfs_log_in_any_superblock(self):
        primary = "superblock: bytenr=65536\ncsum\t0x1234 [match]\nlog_root\t0\n"
        mirror = primary.replace("65536", "67108864")
        with patch.object(subprocess, "check_output", return_value=primary + mirror) as output:
            guest_scanner.require_clean("/dev/test", "btrfs")
            output.return_value = primary + mirror.replace("log_root\t0", "log_root\t4096")
            with self.assertRaisesRegex(SystemExit, "pending tree log"):
                guest_scanner.require_clean("/dev/test", "btrfs")
            output.return_value = primary + mirror.replace("[match]", "[DON'T MATCH]")
            with self.assertRaisesRegex(SystemExit, "invalid superblock"):
                guest_scanner.require_clean("/dev/test", "btrfs")

    def test_inventory_rejects_modified_bios_partition_before_mount(self):
        layout = {1: "ext4", 16: "ext4", 15: "vfat", 14: None}
        children = [{"name": f"/dev/test{number}", "fstype": kind} for number, kind in layout.items()]
        with (patch.object(subprocess, "check_output", side_effect=["1", json.dumps({
                "blockdevices": [{"children": children}],
        })]), patch.object(subprocess, "run") as run, patch.object(guest_scanner, "partition_digest",
                                                                  return_value="changed") as digest):
            with self.assertRaisesRegex(SystemExit, "BIOS boot partition differs"):
                guest_scanner.collect("worker", "/dev/test", "canonical")
            digest.assert_called_once_with("/dev/test14")
            run.assert_not_called()

    def test_initramfs_ignores_seed_and_timestamps_but_detects_executable_changes(self):
        def entry(name, content, mtime, mode=0o100644):
            fields = (1, mode, 0, 0, 1, mtime, len(content), 0, 0, 0, 0, len(name) + 1, 0)
            header = ("070701" + "".join(f"{value:08x}" for value in fields)).encode()
            prefix = header + name + b"\0"
            return prefix + bytes(-len(prefix) % 4) + content + bytes(-len(content) % 4)

        with tempfile.TemporaryDirectory() as tmp:
            disk = Path(tmp) / "initrd"

            def checksum(seed, executable, timestamp):
                disk.write_bytes(entry(b".random-seed", seed, timestamp) +
                                 entry(b"init", executable, timestamp, 0o100755) +
                                 entry(b"TRAILER!!!", b"", timestamp))
                return initramfs.fingerprint(disk)

            initial = checksum(b"entropy", b"approved", 10)
            self.assertEqual(initial, checksum(b"different", b"approved", 11))
            self.assertNotEqual(initial, checksum(b"entropy", b"changed", 10))

    def test_package_manifest_rejects_duplicate_or_path_bearing_package_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tool-packages.sha256"
            row = "a" * 64 + "  tool.deb\n"
            for invalid in (row * 22, row.replace("tool.deb", "../tool.deb")):
                path.write_text(invalid)
                with self.assertRaisesRegex(SystemExit, "Invalid tool package manifest entry"):
                    first_run_inputs.package_manifest(path, "tool", first_run_inputs.digest(path))

    @staticmethod
    def builder_probe(state, step, groups="991", sudo_output="User otuken-ci-build is not allowed to run sudo on fixture-host.",
                      sudo_status=0, args=()):
        helper = Path(__file__).resolve().parents[1] / "ops/first-run-builder"
        script = r"""
state=$1
source "$2"
subgroups=$3 sudo_output=$4 sudo_status=$5
shift 5
fail() { printf '%s\n' "$*" >&2; exit 1; }
getent() {
    case "$1" in
        passwd) printf 'otuken-ci-build:x:991:991::%s:/usr/sbin/nologin\n' "$build_home" ;;
        group) printf 'otuken-ci-build:x:991:\n' ;;
        shadow) printf 'otuken-ci-build:!:0:0:99999:7:::\n' ;;
    esac
}
id() { if [[ "$1" == -G ]]; then printf '%s\n' "$subgroups"; else printf '1001\n'; fi; }
sudo() { printf '%s\n' "$sudo_output" >&2; return "$sudo_status"; }
"""
        return subprocess.run(["bash", "-eu", "-o", "pipefail", "-c", script + step, "test", str(state), str(helper),
                               groups, sudo_output, str(sudo_status), *args], check=False, capture_output=True, text=True)

    def test_dedicated_builder_refuses_the_origin_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "origin-user").write_text("build-user\n")
            good = self.builder_probe(tmp, "builder_identity")
            bad = self.builder_probe(tmp, "builder_identity", groups="991 1001")
        self.assertEqual((good.returncode, good.stdout), (0, "991:991\n"))
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("Unexpected builder group membership", bad.stderr)

    def test_dedicated_builder_sudo_listing_fails_closed(self):
        granted = "User otuken-ci-build may run the following commands on fixture-host:\n    (ALL) /usr/bin/true"
        with tempfile.TemporaryDirectory() as tmp:
            for status in (0, 1):
                denied = self.builder_probe(tmp, "builder_identity", sudo_status=status)
                self.assertEqual((denied.returncode, denied.stdout), (0, "991:991\n"))
            for output, status, error in (
                (granted, 0, "must have no sudo rule"),
                ("sudo: unable to initialize policy plugin", 1, "Cannot verify"),
                ("", 0, "Cannot verify"),
                ("sudo: policy error\nUser otuken-ci-build is not allowed to run sudo on fixture-host.", 0, "Cannot verify"),
            ):
                with self.subTest(output=output, status=status):
                    outcome = self.builder_probe(tmp, "builder_identity", sudo_output=output, sudo_status=status)
                    self.assertNotEqual(outcome.returncode, 0)
                    self.assertIn(error, outcome.stderr)

    def test_builder_init_records_existing_uid_after_interrupted_account_creation(self):
        script = r"""
build_root=$state/build-root
reserve_inputs() { :; }
stat() { [[ $4 == "$state/origin" ]]; printf 'build-user:700:256\n'; }
useradd() { exit 97; }
mkdir() { [[ $* == "-m 0711 -- $build_root" ]] || exit 96; exit 49; }
builder_init "$state/origin" "$state/reference" "$1" build-user
"""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / "origin").mkdir()
            (state / "reference").write_text("approved reference\n")
            approved = first_run_inputs.digest(state / "reference")
            (state / "builder-intent").write_text(approved + "\n")
            (state / "reviewed-commit").write_text("a" * 40 + "\n")
            result = self.builder_probe(state, script, args=(approved,))
            self.assertEqual(result.returncode, 49, result.stderr)
            self.assertEqual((state / "builder-uid").read_text(), "991:991\n")
            self.assertEqual((state / "origin-user").read_text(), "build-user\n")

    def test_git_archive_stages_owner_modes_even_with_a_group_writable_archive_default(self):
        sources = ("ops/first-run.md", "ops/first-run-builder", "ops/first-run")
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp)
            source = scratch / "source"
            bare = scratch / "release.git"
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            for folder in ("ci/nested", "ops"):
                (source / folder).mkdir(parents=True)
                (source / folder / "fixture").touch()
            subprocess.run(["git", "-C", str(source), "add", "ci", "ops"], check=True)
            subprocess.run(["git", "-C", str(source), "-c", "user.name=Fixture", "-c", "user.email=fixture@localhost",
                            "-c", "commit.gpgsign=false", "commit", "-qm", "Fixture"], check=True)
            subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], check=True)
            subprocess.run(["git", f"--git-dir={bare}", "config", "tar.umask", "002"], check=True)
            setup = r"""
umask 077
scratch=$1 stage=$2 temp=$stage commit=HEAD ref=$commit
g() { git --git-dir="$scratch/release.git" "$@"; }
git_local() { g "$@"; }
# GNU tar preserves permissions by default when the host owner runs as root.
tar() { command tar --same-permissions "$@"; }
"""
            for index, path in enumerate(sources):
                with self.subTest(path=path):
                    line, = [line.strip() for line in (repo / path).read_text().splitlines()
                             if " archive " in line and "| tar --no-same-owner -xf" in line]
                    stage = scratch / str(index)
                    target = stage / "recipe" if path.endswith("builder") else stage
                    target.mkdir(mode=0o700, parents=True)
                    subprocess.run(["bash", "-eu", "-o", "pipefail", "-c", setup + line, "test", tmp, str(stage)],
                                   check=True)
                    for folder in ("ci", "ci/nested", "ops"):
                        info = (target / folder).stat()
                        self.assertEqual((info.st_uid, info.st_mode & 0o7777), (os.getuid(), 0o755))

    def test_builder_retirement_requires_admitted_media_and_keeps_reference(self):
        helper = Path(__file__).resolve().parents[1] / "ops/first-run-builder"
        script = r"""
state=$1
source "$2"
fixtures=$state/fixtures
build_recipe=$state/recipe
fail() { printf '%s\n' "$*" >&2; exit 1; }
derived() { [[ $1 == "$build_home/media" && $2 == reviewed ]] && printf 'verified\n'; }
builder_cleanup() {
    [[ $(<"$state/fixture-reference.json") == pin ]]
    if [[ -d $build_recipe ]]; then rm -r -- "$build_recipe"; fi
}
mkdir -p "$fixtures" "$build_recipe"
printf 'pin\n' > "$build_recipe/reviewed-reference.json"
if (builder_retire); then exit 5; fi
[[ ! -e $state/fixture-reference.json && -d $build_recipe ]]
printf 'reviewed\n' > "$state/fixture-approval"
touch "$fixtures/IMAGES.sha256.sig"
builder_retire
builder_retire
[[ ! -e $build_recipe && $(stat -c %a "$state/fixture-reference.json") == 600 ]]
"""
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(["bash", "-eu", "-c", script, "test", tmp, str(helper)],
                                    capture_output=True, text=True, check=True)
            self.assertIn("Admit the reviewed fixture media", result.stderr)
            self.assertEqual(result.stdout.count("Dedicated builder retired"), 2)

    def test_nested_evidence_requires_every_positive_and_negative_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "isolation.serial.log"
            lines = [f"{tier} {case} passed" for tier in ("T4", "T5", "T6") for case in sorted(getattr(isolation, tier))]
            log.write_text("\n".join(lines) + "\n")
            provenance.isolation_evidence(log)
            log.write_text("\n".join(lines[:-1]) + "\n")
            with self.assertRaisesRegex(SystemExit, "every successful case"):
                provenance.isolation_evidence(log)

    def test_topology_exercises_distinct_projects_and_all_gate_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            topology.make(folder)
            record = json.loads((folder / "topology.json").read_text())
            self.assertNotEqual(record["guests"]["worker-a"][0], record["guests"]["worker-b"][0])
            for label in ("t4", "t5", "t6"):
                self.assertEqual(set(record[label]), getattr(isolation, label.upper()))
                if label != "t4":
                    self.assertTrue(all(check["control"] != "worker-a" for check in record[label].values()))
            self.assertGreaterEqual(len(record["canary"]), 24)

    def test_provenance_refuses_to_attest_when_nested_validation_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            logs = work / "logs"
            logs.mkdir()
            for name, marker in provenance.BOOT_LOGS.items():
                (logs / name).write_text(marker)
            (logs / "isolation.serial.log").write_text("nested KVM was unavailable")
            with self.assertRaisesRegex(SystemExit, "missing successful evidence"):
                provenance.make(work, "e" * 40, work / "reference.json")
            self.assertFalse((work / "media/PROVENANCE.json").exists())

    def test_firewall_check_distinguishes_admission_membership_from_policy_changes(self):
        rules = {"nftables": [{"set": {"name": "fixture", "elem": ["allowed"]}},
                             {"rule": {"chain": "input", "expr": [{"accept": None}]}}]}
        changed = json.loads(json.dumps(rules))
        changed["nftables"][0]["set"]["elem"] = ["new"]
        self.assertEqual(first_run_health.firewall_shape(json.dumps(rules)),
                         first_run_health.firewall_shape(json.dumps(changed)))
        baseline = {"ssh": True, "dns": True, "http_probe": None, "resolver_link": "stub",
                    "firewall": first_run_health.firewall_shape(json.dumps(rules)), "listeners": ["stable"]}
        self.assertTrue(first_run_health.compare(baseline, {**baseline, "listeners": ["other"]}))
        probed = {**baseline, "http_probe": {"url": "http://127.0.0.1:8080/", "status": "200"}}
        self.assertFalse(first_run_health.compare(probed, probed))
        with self.assertRaisesRegex(SystemExit, "HTTP health probe"):
            first_run_health.compare(probed, {**probed, "http_probe": {"url": "http://127.0.0.1:8080/", "status": "503"}})
        self.assertIsNone(first_run_health.validate_url(""))
        with self.assertRaisesRegex(SystemExit, "Invalid optional HTTP"):
            first_run_health.validate_url("file:///etc/passwd")
        changed["nftables"][1]["rule"]["expr"] = [{"drop": None}]
        with self.assertRaisesRegex(SystemExit, "firewall policy"):
            first_run_health.compare(baseline,
                                     {**baseline, "firewall": first_run_health.firewall_shape(json.dumps(changed))})

    def test_cleanup_refuses_objects_without_run_scoped_evidence(self):
        name = "first-clean"
        instances = [{"name": "otuken-ci-test", "config": {"user.otuken-ci-run": name}}]
        images = [{"fingerprint": "a" * 64}]
        receipt = "otuken-ci-ext4 " + "a" * 64
        self.assertEqual(ci_residue.owned_objects(instances, images, name, receipt),
                         [("vm", "otuken-ci-test"), ("image", "a" * 64)])
        with self.assertRaisesRegex(SystemExit, "Unrecognized instance"):
            ci_residue.owned_objects(instances, images, "another-run", receipt)
        with self.assertRaisesRegex(SystemExit, "Unrecognized image"):
            ci_residue.owned_objects(instances, images, name, "")
