# SPDX-License-Identifier: MIT
"""Pre-update checkpoints for product-owned config and data."""

import ctypes
import os
import re
import shutil
import stat
import subprocess
import tarfile
import uuid
from pathlib import Path

from common import require, sync_dir

# Live work, audit history and installer recovery records survive rollback.
RESTORE_STAGE = ".otuken-restore"
CHECKPOINT = re.compile(r"[0-9a-f]{32}")
PRESERVED = {"vault", "projects", "hq", "audit", "journal", "evidence", "backups", "control"}


def run(*command):
    subprocess.run(command, check=True)


def check_floor(paths, floor):
    for parent in (paths.config.parent, paths.data.parent):
        usage = shutil.disk_usage(parent)
        require(usage.free * 100 >= usage.total * floor, f"Backup disk floor reached at {parent}")


def members(source, exclude):
    return sorted(path.name for path in source.iterdir() if path.name not in exclude and path.name != RESTORE_STAGE)


def verify_tree(source, exclude, *, btrfs=False):
    def inspect(part):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode):
            return
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),
                "Checkpoint contains a special file")
        require(not part.is_mount(), "Checkpoint cannot include a nested mount")
        require(not (btrfs and stat.S_ISDIR(info.st_mode) and info.st_ino == 256),
                "Checkpoint cannot include a nested btrfs subvolume")

    for name in members(source, exclude):
        inspect(source / name)
        for parent, dirs, files in os.walk(source / name, followlinks=False):
            for child in dirs + files:
                inspect(Path(parent) / child)


def export(source, target, exclude):
    names = b"".join(os.fsencode(name) + b"\0" for name in members(source, exclude))
    subprocess.run(
        ["/usr/bin/tar", "--acls", "--xattrs", "--numeric-owner", "--sparse",
         "--one-file-system", "-C", str(source), "-cf", str(target), "--null",
         "--verbatim-files-from", "--files-from=-"],
        input=names, check=True,
    )
    with target.open("rb") as stream:
        os.fsync(stream.fileno())


def remove_tree(path, btrfs):
    for name in ("config", "data"):
        child = path / name
        if btrfs and child.is_dir():
            run("/usr/bin/btrfs", "subvolume", "delete", str(child))
    shutil.rmtree(path)


def create(paths, floor):
    check_floor(paths, floor)
    root = paths.data / "backups"
    btrfs = paths.fs == "btrfs"
    for old in root.iterdir():
        if re.fullmatch(r"\.pending-[0-9a-f]{32}", old.name):
            require(old.is_dir() and not old.is_symlink(), "Unsafe interrupted checkpoint")
            remove_tree(old, btrfs)
    identifier = uuid.uuid4().hex
    pending = root / (".pending-" + identifier)
    pending.mkdir(mode=0o700)
    try:
        for name, source, exclude in (("config", paths.config, set()),
                                      ("data", paths.data, PRESERVED)):
            verify_tree(source, exclude, btrfs=btrfs)
            if btrfs:
                run("/usr/bin/btrfs", "subvolume", "snapshot", "-r", str(source), str(pending / name))
            else:
                export(source, pending / (name + ".tar"), exclude)
        check_floor(paths, floor)
        sync_dir(pending)
        pending.rename(root / identifier)
        sync_dir(root)
    finally:
        if pending.exists():
            remove_tree(pending, btrfs)
    return identifier


def remove(paths, identifier):
    require(CHECKPOINT.fullmatch(identifier), "Invalid checkpoint ID")
    root = paths.data / "backups"
    path = root / identifier
    if path.is_dir() and not path.is_symlink():
        remove_tree(path, paths.fs == "btrfs")
        sync_dir(root)


def prune(paths, protected=(), keep=3):
    root = paths.data / "backups"
    known = [path for path in root.iterdir()
             if CHECKPOINT.fullmatch(path.name) and path.is_dir() and not path.is_symlink()]
    recent = sorted(known, key=lambda path: path.stat().st_mtime_ns, reverse=True)[:keep]
    retained = {*protected, *(path.name for path in recent)}
    for path in known:
        if path.name not in retained:
            remove(paths, path.name)


def final_export(paths, identifier, floor, *, legacy=False):
    require(CHECKPOINT.fullmatch(identifier), "Invalid checkpoint ID")
    dest = paths.data.parent / f"otuken-purge-{identifier}"
    if dest.exists() or dest.is_symlink():
        info = dest.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700
                and all((dest / name).is_file() and not (dest / name).is_symlink()
                        for name in ("config.tar", "data.tar")), "Unsafe purge checkpoint")
        if legacy:
            scrub_legacy_export(paths, dest, floor)
        return dest
    pending = dest.with_name("." + dest.name)
    discard_stage(pending)
    check_floor(paths, floor)
    pending.mkdir(mode=0o700)
    try:
        for label, source, exclude in (
            ("config", paths.config, set()),
            ("data", paths.data, {"backups", "credentials", "control"}),
        ):
            verify_tree(source, exclude, btrfs=paths.fs == "btrfs")
            export(source, pending / (label + ".tar"), exclude)
        check_floor(paths, floor)
        sync_dir(pending)
        pending.rename(dest)
        sync_dir(dest.parent)
    finally:
        discard_stage(pending)
    return dest


def scrub_legacy_export(paths, destination, floor):
    archive = destination / "data.tar"
    excluded = {"credentials", "control"}
    with tarfile.open(archive) as previous:
        if not any(Path(member.name).parts[:1] and Path(member.name).parts[0] in excluded
                   for member in previous):
            return
    check_floor(paths, floor)
    staging = destination / ".data.tar.rewrite"
    staging.unlink(missing_ok=True)
    try:
        with staging.open("xb") as output, tarfile.open(archive, mode="r|") as previous:
            with tarfile.open(fileobj=output, mode="w|", format=tarfile.PAX_FORMAT) as clean:
                for member in previous:
                    if Path(member.name).parts[:1] and Path(member.name).parts[0] in excluded:
                        continue
                    clean.addfile(member, previous.extractfile(member) if member.isfile() else None)
            output.flush()
            os.fsync(output.fileno())
        staging.replace(archive)
        sync_dir(destination)
    finally:
        staging.unlink(missing_ok=True)


def clean_legacy_stages(paths):
    for parent in (paths.config.parent, paths.data.parent):
        for stage in parent.glob(".otuken-restore-*"):
            if re.fullmatch(r"\.otuken-restore-[a-z0-9_]{8}", stage.name):
                discard_stage(stage)


def discard_stage(path):
    if path.exists() or path.is_symlink():
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700, "Unsafe checkpoint staging directory")
        shutil.rmtree(path)
        sync_dir(path.parent)


def exchange(staged, target):
    """Atomically swap entries, including nonempty directories on Linux."""
    rename = ctypes.CDLL(None, use_errno=True).renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    if rename(-100, os.fsencode(staged), -100, os.fsencode(target), 2):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def restore(paths, identifier):
    require(CHECKPOINT.fullmatch(identifier), "Invalid checkpoint ID")
    root = paths.data / "backups" / identifier
    require(root.is_dir() and not root.is_symlink(), "Checkpoint is missing")
    targets = (("config", paths.config, set()), ("data", paths.data, PRESERVED))
    # Stage both trees before touching either. Entries never cross subvolume boundaries.
    try:
        for name, dest, exclude in targets:
            stage = dest / RESTORE_STAGE
            discard_stage(stage)
            verify_tree(dest, exclude, btrfs=paths.fs == "btrfs")
            stage.mkdir(mode=0o700)
            if paths.fs == "btrfs":
                for part in members(root / name, exclude):
                    run("/usr/bin/cp", "-a", "--reflink=auto", "--", str(root / name / part), str(stage))
            else:
                run("/usr/bin/tar", "--acls", "--xattrs", "--xattrs-include=*", "--numeric-owner",
                    "-xf", str(root / (name + ".tar")), "-C", str(stage))
            require(not ({entry.name for entry in stage.iterdir()} & (exclude | {RESTORE_STAGE})),
                    "Unexpected preserved entry in checkpoint")
        for _, dest, exclude in targets:
            stage = dest / RESTORE_STAGE
            extras = set(members(dest, exclude)) - set(members(stage, set()))
            for child in list(stage.iterdir()):
                target = dest / child.name
                if target.exists() or target.is_symlink():
                    exchange(child, target)
                else:
                    child.rename(target)
            sync_dir(dest)
            # Remove entries absent from the checkpoint only after replacements are in place.
            removed = stage / RESTORE_STAGE
            removed.mkdir(mode=0o700)
            for name in extras:
                (dest / name).rename(removed / name)
            sync_dir(dest)
    finally:
        for _, dest, _ in targets:
            discard_stage(dest / RESTORE_STAGE)
