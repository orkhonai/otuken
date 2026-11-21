# SPDX-License-Identifier: MIT
"""Verify release signatures before opening any archive member."""

import base64
import hashlib
import io
import os
import re
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from common import digest, require

VERSION = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)
NAMESPACE = "otuken-release"
RUNTIME = {"otuken", "version", "engine/common.py", "engine/main.py",
           "engine/release.py", "engine/install.py", "engine/backup.py",
           "engine/guard.py", "engine/transport.py", "LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md",
           "docs/THIRD-PARTY-TOOLS.md"}
RUNTIME_EXTRA = {"engine/audit.py", "engine/breakglass.py", "bin/otuken", "bin/otukenctl",
                 "install/systemd/otuken-guard-request.service",
                 "default/guard-policy.json", "default/installer.json"}
MAX_ARCHIVE = 64 * 1024 * 1024


def version_key(version):
    match = VERSION.fullmatch(version) if isinstance(version, str) and len(version) <= 100 else None
    require(match, "Invalid semantic version")
    pre = match[4].split(".") if match[4] else []
    require(all(not p.isdigit() or len(p) == 1 or not p.startswith("0") for p in pre),
            "Invalid numeric prerelease identifier")
    return (*(int(match[i]) for i in (1, 2, 3)), not pre,
            tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre))


def read_limited(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit, "Invalid signed input file")
        data = stream.read(limit + 1)
        require(len(data) <= limit, "Signed input exceeds its size limit")
        return data


def signer(raw):
    fields = raw.split()
    require(len(raw) <= 4096 and len(raw.splitlines()) == 1 and len(fields) >= 3
            and fields[:2] == [b"otuken-release", b"ssh-ed25519"], "Expected one ED25519 release signer")
    key = base64.b64decode(fields[2], validate=True)
    require(len(key) == 51 and key.startswith(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20"),
            "Invalid ED25519 release key")
    fingerprint = base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip("=")
    canonical = b"otuken-release ssh-ed25519 " + base64.b64encode(key) + b"\n"
    return canonical, "SHA256:" + fingerprint


def signed(data, signature, signers, namespace=NAMESPACE):
    # Verify the same immutable bytes inspected for pinning, never reopen the offered signer path.
    with tempfile.TemporaryDirectory(prefix="otuken-verify-") as scratch:
        pinned = Path(scratch) / "allowed_signers"
        pinned.write_bytes(signers)
        signature_copy = Path(scratch) / "signature"
        signature_copy.write_bytes(read_limited(signature, 65536))
        result = subprocess.run(
            ["/usr/bin/ssh-keygen", "-Y", "verify", "-f", str(pinned), "-I",
             "otuken-release", "-n", namespace, "-s", str(signature_copy)],
            input=data, capture_output=True, check=False, timeout=15,
        )
    require(result.returncode == 0, f"Invalid SSH signature ({namespace})")


@dataclass(frozen=True)
class Release:
    version: str
    checksum: str
    files: dict


def verify(archive, sums, signature, signers):
    data = read_limited(sums, 65536)
    signed(data, signature, signers)
    name = archive.name
    require(name.startswith("otuken-") and name.endswith(".tar.gz"), "Unexpected archive name")
    version = name[len("otuken-"):-len(".tar.gz")]
    version_key(version)
    entries = re.findall(rb"^([0-9a-f]{64}) [ *]([^\r\n]+)$", data, re.MULTILINE)
    matches = [checksum.decode() for checksum, filename in entries if filename == name.encode()]
    require(len(matches) == 1, "Expected one signed checksum for the release")
    packed = read_limited(archive, MAX_ARCHIVE)
    require(digest(packed) == matches[0], "Release checksum mismatch")

    files = {}
    seen = set()
    unpacked = 0
    prefix = f"otuken-{version}"
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz") as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            parts = path.parts
            require(parts and parts[0] == prefix and ".." not in parts,
                    "Archive member outside the release directory")
            relative = "/".join(parts[1:])
            require(relative not in seen and (member.isfile() or member.isdir()),
                    "Unexpected archive member type or duplicate")
            seen.add(relative)
            unpacked += member.size
            require(unpacked <= MAX_ARCHIVE and len(seen) <= 10000, "Release contents exceed limits")
            migration = re.fullmatch(r"migrations/[0-9]{10}\.py", relative)
            if relative in (RUNTIME | RUNTIME_EXTRA) or migration:
                require(member.isfile() and member.size <= 1024 * 1024, "Invalid runtime file")
                with bundle.extractfile(member) as source:
                    files[relative] = source.read()
    require(RUNTIME <= files.keys() and files["version"].decode().strip() == version,
            "Release is missing runtime files or has an inconsistent version")
    return Release(version, matches[0], files)


def channel(path, signature, signers, selected, release):
    import json

    data = read_limited(path, 65536)
    signed(data, signature, signers, "otuken-channel")
    row = json.loads(data)
    require(isinstance(row, dict) and set(row) == {"channel", "version", "sha256", "expires"},
            "Invalid channel metadata")
    require(row["channel"] == selected and row["version"] == release.version
            and row["sha256"] == release.checksum, "Channel does not name this release")
    require(isinstance(row["expires"], str)
            and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
                             row["expires"]), "Invalid channel expiry")
    expires = datetime.strptime(row["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    require(expires > datetime.now(UTC), "Channel metadata expired")
    if selected == "stable":
        require(version_key(release.version)[3], "Stable channel cannot contain a prerelease")
    return hashlib.sha256(data).hexdigest()


def release_paths(directory, version):
    version_key(version)
    return (Path(directory) / f"otuken-{version}.tar.gz",
            Path(directory) / "SHA256SUMS", Path(directory) / "SHA256SUMS.sig")
