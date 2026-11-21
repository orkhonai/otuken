# SPDX-License-Identifier: MIT
"""Copy only named offline CI inputs into an owner-controlled snapshot."""

import os
import re
import stat
import sys
from pathlib import Path

MIB = 1024**2
IMAGE_LIMITS = {
    **{f"{fs}.metadata.tar.xz": MIB for fs in ("ext4", "btrfs")},
    **{f"{fs}.disk.qcow2": 8192 * MIB for fs in ("ext4", "btrfs")},
    "IMAGES.sha256": 65536,
    "IMAGES.sha256.sig": 65536,
}
SIGNERS = ("image", "release")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9.+-]+)?")


def trusted(path):
    for part in [path, *path.parents]:
        info = part.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or part.is_symlink():
            raise SystemExit(f"Untrusted CI host path: {part}")


def copy(source_fd, name, destination, limit):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source_fd)
    with os.fdopen(fd, "rb") as src:
        info = os.fstat(src.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise SystemExit(f"Invalid staged fixture: {name}")
        with destination.open("xb") as out:
            copied = 0
            while data := src.read(1024 * 1024):
                copied += len(data)
                if copied > limit:
                    raise SystemExit(f"Fixture became too large: {name}")
                out.write(data)


def stage(source, work, policy=Path("/etc/otuken-ci")):
    trusted(work)
    for label in SIGNERS:
        path = policy / f"{label}.allowed_signers"
        trusted(path)
        limit = 16384
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        if not data or len(data) > limit:
            raise SystemExit("Invalid pinned signer file")
        (work / f"{label}.allowed_signers").write_bytes(data)
    root = os.open(source, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name, limit in IMAGE_LIMITS.items():
            copy(root, name, work / name, limit)
        for label in ("previous", "candidate"):
            directory = work / label
            directory.mkdir(mode=0o700)
            fd = os.open(label, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
            try:
                copy(fd, "version", directory / "version", 128)
                version = (directory / "version").read_text().strip()
                if not VERSION.fullmatch(version):
                    raise SystemExit("Invalid staged release version")
                copy(fd, f"otuken-{version}.tar.gz", directory / f"otuken-{version}.tar.gz", 64 * MIB)
                for name in ("SHA256SUMS", "SHA256SUMS.sig", "rc.json", "rc.json.sig"):
                    if label == "candidate" or name.startswith("SHA256SUMS"):
                        copy(fd, name, directory / name, 65536)
            finally:
                os.close(fd)
    finally:
        os.close(root)


if __name__ == "__main__":
    stage(Path(sys.argv[1]), Path(sys.argv[2]))
