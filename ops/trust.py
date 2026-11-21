# SPDX-License-Identifier: MIT
"""Check ownership, modes and reviewed bytes of the host-side CI runner."""

import ctypes
import hashlib
import os
import re
import shutil
import stat
import sys
from pathlib import Path

RUNNER = Path("/opt/otuken-ci/runner")
ANCHORS = Path("/etc/otuken-ci")
ANCHOR_FILES = {"release.allowed_signers", "image.allowed_signers"}


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def trusted(path, *, directories=False, uid=0):
    info = path.lstat()
    allowed = stat.S_ISDIR(info.st_mode) if directories else stat.S_ISREG(info.st_mode)
    modes = {0o700, 0o755} if directories else {0o600, 0o644, 0o700, 0o755}
    require(allowed and info.st_uid == uid and stat.S_IMODE(info.st_mode) in modes,
            f"Untrusted CI host path: {path}")


def ancestry(directory):
    for part in [directory, *directory.parents]:
        trusted(part, directories=True)


def verify_runner(directory, *, uid=0):
    manifest = directory / ".runner-sha256"
    reviewed = directory / ".reviewed-commit"
    for path in (manifest, reviewed):
        trusted(path, uid=uid)
    require(re.fullmatch(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\n", reviewed.read_text()), "Invalid reviewed commit record")
    expected = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r"([a-f0-9]{64})  (.*)", line)
        require(match and match[2] not in expected, "Invalid runner checksum manifest")
        expected[match[2]] = match[1]
    require({".reviewed-commit", "ci/run", "ci/preflight.py", "ops/trust.py", "ops/incus-host"} <= expected.keys(),
            "Runner manifest is incomplete")
    found = set()
    for path in directory.rglob("*"):
        if path == manifest:
            continue
        relative = path.relative_to(directory).as_posix()
        if path.is_dir() and not path.is_symlink():
            trusted(path, directories=True, uid=uid)
            continue
        trusted(path, uid=uid)
        with path.open("rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == expected.get(relative),
                    f"Runner checksum mismatch: {relative}")
        found.add(relative)
    require(found == expected.keys(), "Runner manifest references missing files")


def remove_ci_paths(runner=RUNNER, anchors=ANCHORS, *, uid=0):
    base = runner.parent
    def present(path):
        return path.exists() or path.is_symlink()
    if present(base):
        trusted(base, directories=True, uid=uid)
        require({path.name for path in base.iterdir()} <= {runner.name}, "Unexpected CI runner entries")
        if present(runner):
            trusted(runner, directories=True, uid=uid)
            verify_runner(runner, uid=uid)
    if present(anchors):
        trusted(anchors, directories=True, uid=uid)
        require({path.name for path in anchors.iterdir()} <= ANCHOR_FILES, "Unexpected CI trust entries")
        for path in anchors.iterdir():
            trusted(path, uid=uid)
    if present(base):
        if present(runner):
            shutil.rmtree(runner)
        base.rmdir()
    if present(anchors):
        for path in anchors.iterdir():
            path.unlink()
        anchors.rmdir()


def replace_runner(stage, current):
    verify_runner(stage)
    verify_runner(current)
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    if rename(-100, os.fsencode(stage), -100, os.fsencode(current), 2):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def main():
    if sys.argv[1:] == ["cleanup"]:
        ancestry(RUNNER.parent.parent)
        ancestry(ANCHORS.parent)
        remove_ci_paths()
        print("CI runner and trust anchors removed")
        return
    action, supplied = sys.argv[1:]
    directory = Path(supplied)
    ancestry(directory)
    if action in {"runner", "replace"}:
        require(directory == RUNNER or (directory.parent == RUNNER.parent and directory.name.startswith(".runner-")),
                "Runner must be installed in the owner-controlled path")
        if action == "replace":
            require(directory != RUNNER, "Expected a newly verified runner staging directory")
            ancestry(RUNNER)
            replace_runner(directory, RUNNER)
        else:
            verify_runner(directory)
    elif action == "maintenance":
        require(directory.parent == Path("/root") and re.fullmatch(r"otuken-incus\.[A-Za-z0-9]{8}", directory.name),
                "Untrusted maintenance evidence path")
        for name in ("incus-host", "host_state.py", "trust.py"):
            trusted(directory / name)
    else:
        raise SystemExit("Unknown CI trust check")


if __name__ == "__main__":
    main()
