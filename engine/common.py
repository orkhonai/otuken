# SPDX-License-Identifier: MIT
"""Filesystem and serialization primitives shared by the installer and guard."""

import contextlib
import fcntl
import hashlib
import json
import os
import stat
import tempfile


class Error(Exception):
    pass


def require(condition, message):
    if not condition:
        raise Error(message)


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data, mode=0o600):
    # Compare-before-write and same-directory atomic publication pattern.
    if path.is_file() and not path.is_symlink():
        info = path.stat()
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) == (
            os.geteuid(), os.getegid(), mode
        ) and path.read_bytes() == data:
            return
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path, default=None):
    if not path.exists() and not path.is_symlink():
        return default
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and not info.st_mode & 0o022, f"Unsafe file: {path}")
    return json.loads(path.read_bytes())


@contextlib.contextmanager
def lock(path, *, shared=False):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                and not info.st_mode & 0o077, f"Unsafe lock: {path}")
        fcntl.flock(fd, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)
