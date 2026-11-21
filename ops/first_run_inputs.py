# SPDX-License-Identifier: MIT
"""Validate the upstream and derived image provenance for the first CI run."""

import hashlib
import json
import os
import re
import stat
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops import fixture_manifest as inventories

UBUNTU_KEY = "D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81"
UBUNTU_IMAGE = "ubuntu-24.04-server-cloudimg-amd64.img"
KEYRING = "/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg"
FILES = {"ext4.metadata.tar.xz", "ext4.disk.qcow2", "btrfs.metadata.tar.xz", "btrfs.disk.qcow2"}
HEX = re.compile(r"[0-9a-f]{64}")
PACKAGE_COUNTS = {"tool": 22, "guest": 216}
PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9%:+.~_-]*\.deb")


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def digest(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), f"Expected regular file: {path.name}")
        return hashlib.file_digest(stream, "sha256").hexdigest()


def signed_checksum(status, contents, filename):
    records = [line.split()[2:] for line in status.splitlines() if line.startswith("[GNUPG:] VALIDSIG ")]
    require(any(row and (row[0] == UBUNTU_KEY or (len(row) == 10 and row[9] == UBUNTU_KEY))
                for row in records), "Ubuntu checksum signature does not match the pinned primary key")
    matches = []
    for line in contents.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match and match[2].removeprefix("./") == filename:
            matches.append(match[1])
    require(len(matches) == 1, "Expected exactly one signed Ubuntu image checksum")
    return matches[0]


def ubuntu(directory, serial):
    require(re.fullmatch(r"[0-9]{8}", serial), "Use a dated Ubuntu release serial (YYYYMMDD)")
    result = subprocess.run(
        ["/usr/bin/gpgv", "--status-fd", "1", "--keyring", KEYRING,
         str(directory / "SHA256SUMS.gpg"), str(directory / "SHA256SUMS")],
        capture_output=True, text=True, check=False, timeout=30,
    )
    require(result.returncode == 0, "Canonical's detached checksum signature did not verify")
    expected = signed_checksum(result.stdout, (directory / "SHA256SUMS").read_text(), UBUNTU_IMAGE)
    require(digest(directory / UBUNTU_IMAGE) == expected, "Ubuntu image checksum mismatch")
    return {"serial": serial, "filename": UBUNTU_IMAGE, "sha256": expected, "primary_fingerprint": UBUNTU_KEY}


def standalone_disk(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Expected a regular QCOW2 file")
        header = stream.read(104)
    require(len(header) == 104 and header[:4] == b"QFI\xfb", f"Invalid QCOW2 header: {path.name}")
    version, backing_offset, backing_length, _, virtual_size, encryption = struct.unpack_from(">IQIIQI", header, 4)
    require(version in {2, 3} and not backing_offset and not backing_length and not encryption
            and 0 < virtual_size <= 32 * 1024**3, f"Fixture disk must be standalone and fit its CI profile: {path.name}")
    if version == 3:
        flags, = struct.unpack_from(">Q", header, 72)
        require(not flags & (1 << 2), f"Fixture disk has an external data file: {path.name}")


def hash_map(value, keys=None):
    return (isinstance(value, dict) and (keys is None or value.keys() == keys)
            and all(isinstance(checksum, str) and HEX.fullmatch(checksum) for checksum in value.values()))


def reference(path, expected=None):
    raw = path.read_bytes()
    require(len(raw) <= 65536 and (expected is None or hashlib.sha256(raw).hexdigest() == expected),
            "Reviewed fixture reference SHA-256 mismatch")
    value = json.loads(raw)
    require(isinstance(value, dict) and value.get("schema") == 2
            and hash_map(value.get("manifests"), set(inventories.ROLES))
            and hash_map(value.get("package_manifest_sha256"), PACKAGE_COUNTS.keys())
            and all(isinstance(value.get(key), str) and HEX.fullmatch(value[key])
                    for key in ("recipe_sha256", "agent_build_recipe_sha256", "agent_inventory_recipe_sha256"))
            and value.get("allowlist") == inventories.allowlist(),
            "Invalid fixture reference")
    upstream = value.get("ubuntu")
    require(isinstance(upstream, dict) and upstream.get("primary_fingerprint") == UBUNTU_KEY
            and upstream.get("filename") == UBUNTU_IMAGE and re.fullmatch(r"[0-9]{8}", upstream.get("serial", ""))
            and HEX.fullmatch(upstream.get("sha256", "")), "Invalid reviewed Ubuntu receipt")
    return value


def package_manifest(path, kind, expected):
    raw = path.read_bytes()
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == expected,
            f"Reviewed {kind} package manifest mismatch")
    checksums = {}
    for line in raw.decode("ascii").splitlines():
        checksum, separator, name = line.partition("  ")
        require(separator and HEX.fullmatch(checksum) and PACKAGE_NAME.fullmatch(name)
                and name not in checksums, f"Invalid {kind} package manifest entry")
        checksums[name] = checksum
    require(len(checksums) == PACKAGE_COUNTS[kind], f"Wrong {kind} package count")
    return checksums


def recipe():
    root = Path(__file__).resolve().parents[1]
    files = [root / file for file in ("ci/fixture-apt", "ci/fixture-build", "ci/fixture-fetch", "ci/isolation.py",
                                     "ops/first_run_inputs.py", "ops/fixture_manifest.py", "ops/fixture-allowlist.json")]
    files.extend(path for path in sorted((root / "ci/fixture").iterdir()) if path.is_file())
    return "".join(f"{digest(path)}  {path.relative_to(root)}\n" for path in files)


def media_hashes(directory):
    return {name: digest(directory / name) for name in sorted(FILES)}


def check_inventoried_media(work):
    images = media_hashes(work / "media")
    stamp = (work / "manifests/images.sha256").read_text().splitlines()
    require(sorted(stamp) == sorted(f"{sha}  {name}" for name, sha in images.items()),
            "Media changed since guest inventory export")
    return images


def manifest_paths(directory, prefix=""):
    return {role: directory / f"{prefix}{role}.json.gz" for role in inventories.ROLES}


def matches_reference(work, reviewed, agent):
    require(digest(work / "manifests/recipe.sha256") == reviewed["recipe_sha256"],
            "Cold inventory recipe differs from the reviewed recipe")
    check_inventoried_media(work)
    return inventories.evidence(manifest_paths(agent), manifest_paths(work / "manifests"), reviewed["manifests"])


def candidate_reference(work):
    manifest = {kind: digest(work / f"{kind}-packages.sha256") for kind in PACKAGE_COUNTS}
    for kind, expected in manifest.items():
        package_manifest(work / f"{kind}-packages.sha256", kind, expected)
    check_inventoried_media(work)
    manifest_stamp = work / "manifests/recipe.sha256"
    root = Path(__file__).resolve().parents[1]
    # An older scrubbed agent image can be inventoried with the current scanner.
    for name in ("ci/fixture/manifest-guest.py", "ci/fixture/initramfs.py", "ci/fixture/boot-check"):
        require(f"{digest(root / name)}  {name}" in manifest_stamp.read_text().splitlines(),
                "Export the agent inventories with the current guest scanner")
    return {"schema": 2, "ubuntu": json.loads((work / "ubuntu/receipt.json").read_text()),
            "recipe_sha256": hashlib.sha256(recipe().encode()).hexdigest(), "package_manifest_sha256": manifest,
            "agent_build_recipe_sha256": digest(work / "fixture-recipe.sha256"),
            "agent_inventory_recipe_sha256": digest(manifest_stamp),
            "allowlist": inventories.allowlist(),
            "manifests": {role: inventories.load(path, role)[1]
                          for role, path in manifest_paths(work / "manifests").items()}}


def approved_inputs(directory, approved, upstream, reviewed_commit, reviewed, builder):
    require(HEX.fullmatch(approved), "Supply the independently reviewed provenance SHA-256")
    with (directory / "PROVENANCE.json").open("rb") as stream:
        raw = stream.read(65537)
    require(len(raw) <= 65536 and hashlib.sha256(raw).hexdigest() == approved,
            "Derived-image provenance SHA-256 mismatch")
    value = json.loads(raw)
    require(isinstance(value, dict) and value.get("schema") == 4 and value.get("ubuntu") == upstream == reviewed["ubuntu"],
            "Derived images do not name the verified Canonical image")
    checksums = value.get("images")
    require(hash_map(checksums, FILES), "Wrong offline fixture file set")
    build = value.get("build")
    require(isinstance(build, dict) and build.get("commit") == reviewed_commit and build.get("builder") == builder
            and build.get("reference_sha256") == reviewed["sha256"]
            and build.get("recipe_sha256") == reviewed["recipe_sha256"],
            "Fixture recipe must match the reviewed commit")
    packages = build.get("packages")
    require(isinstance(packages, dict) and packages.keys() == PACKAGE_COUNTS.keys(), "Missing package evidence")
    for kind, count in PACKAGE_COUNTS.items():
        entries = packages[kind]
        require(hash_map(entries) and len(entries) == count and all(PACKAGE_NAME.fullmatch(name) for name in entries),
                f"Invalid {kind} package evidence")
        manifest = "".join(f"{checksum}  {name}\n" for name, checksum in sorted(entries.items())).encode()
        require(hashlib.sha256(manifest).hexdigest() == reviewed["package_manifest_sha256"][kind],
                f"{kind} package evidence differs from reviewed inputs")
    isolation = value.get("isolation")
    require(isinstance(isolation, dict) and isolation.get("status") == "passed"
            and isinstance(isolation.get("log_sha256"), str) and HEX.fullmatch(isolation["log_sha256"])
            and value.get("isolation_setup") == "/opt/ci-fixture/isolation-setup",
            "Fixture review requires successful nested isolation evidence")
    boots = isolation.get("boot_sha256")
    require(isinstance(boots, dict) and boots.keys() == {"ext4-boot.serial.log", "btrfs-boot.serial.log"}
            and all(isinstance(checksum, str) and HEX.fullmatch(checksum) for checksum in boots.values()),
            "Fixture review requires both boot evidence hashes")
    evidence = directory / "evidence"
    actual = inventories.evidence(manifest_paths(evidence, "agent."), manifest_paths(evidence, "cold."),
                                  reviewed["manifests"])
    require(actual == value.get("filesystem"), "Provenance inventory evidence differs from the verified comparison")
    require(media_hashes(directory) == checksums, "Cold media bytes differ from the issued provenance")
    for name in sorted(checksums):
        if name.endswith(".qcow2"):
            standalone_disk(directory / name)
    return checksums


def main():
    command, *args = sys.argv[1:]
    if command == "ubuntu":
        receipt = ubuntu(Path(args[0]), args[1])
        print(json.dumps(receipt, sort_keys=True))
    elif command == "derived":
        directory, approved, receipt, commit, reference_path, reference_sha, account, uid = args
        reviewed = reference(Path(reference_path), reference_sha)
        reviewed["sha256"] = reference_sha
        checksums = approved_inputs(Path(directory), approved, json.loads(Path(receipt).read_text()), commit,
                                    reviewed, {"account": account, "uid": int(uid)})
        print("\n".join(f"{checksum}  {name}" for name, checksum in sorted(checksums.items())))
    elif command == "match":
        work, reference_path, agent = map(Path, args)
        print(json.dumps(matches_reference(work, reference(reference_path), agent), sort_keys=True))
    elif command == "verify-agent":
        agent, reference_path = map(Path, args)
        expected = reference(reference_path)["manifests"]
        for role, path in manifest_paths(agent).items():
            require(inventories.load(path, role)[1] == expected[role], f"Reviewed agent inventory changed for {role}")
    elif command == "recipe":
        print(recipe(), end="")
    elif command == "standalone":
        standalone_disk(Path(args[0]))
    elif command == "candidate-reference":
        print(json.dumps(candidate_reference(Path(args[0])), sort_keys=True, indent=2))
    elif command == "package-list":
        root, reference_path, kind = args
        reviewed = reference(Path(reference_path))
        print("\n".join(package_manifest(Path(root) / f"{kind}-packages.sha256", kind,
                                         reviewed["package_manifest_sha256"][kind])))
    else:
        raise SystemExit("Unknown first-run input check")


if __name__ == "__main__":
    main()
