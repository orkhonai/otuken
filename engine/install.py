# SPDX-License-Identifier: MIT
"""Read-only plans and locked, recoverable changes to the product layout."""

import difflib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

import backup
from common import atomic_write, digest, encode, read_json, require, sync_dir
from release import version_key

NAME = "otuken"
EXECUTABLES = {NAME, f"bin/{NAME}", f"bin/{NAME}ctl"}


def safe_dir(path):
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022,
            f"Unsafe directory: {path}")
    return info


def file_mode(path):
    if not path.exists() and not path.is_symlink():
        return None
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and not info.st_mode & 0o022 and info.st_nlink == 1, f"Unsafe file: {path}")
    return stat.S_IMODE(info.st_mode)


class Paths:
    def __init__(self, root=None):
        self.root = Path("/") if root is None else Path(root).absolute()
        self.test = root is not None
        require(self.test == (os.geteuid() != 0),
                "Use a private --root directory for non-root tests or run as the host owner")
        safe_dir(self.root)
        if not self.test:
            info = Path("/etc/os-release").read_text().splitlines()
            require("ID=ubuntu" in info and 'VERSION_ID="24.04"' in info
                    and os.uname().machine == "x86_64" and Path("/sys/fs/cgroup/cgroup.controllers").exists(),
                    "Requires Ubuntu 24.04 amd64 with cgroup v2")
            self.fs = self.filesystem(Path("/"))
            require(self.fs in {"ext4", "btrfs"}, "Supported root filesystems are ext4 and btrfs")
            for component in ("/etc", "/var/lib"):
                require(self.filesystem(Path(component)) == self.fs,
                        "Product config and state must use the root filesystem type")
        else:
            self.fs = "export"
        self.code = self.root / "opt" / NAME
        self.config = self.root / "etc" / NAME
        self.data = self.root / "var/lib" / NAME
        self.cache = self.root / "var/cache" / NAME
        self.runtime = self.root / "run" / NAME
        self.releases = self.code / "releases"
        self.retired = self.code.with_name(f".{NAME}-retired")
        self.current = self.code / "current"
        self.control = self.data / "control"
        self.signers = self.control / "release-signers"
        self.guard_policy = self.config / "guard-policy.json"
        self.purge_record = self.data.with_name(f".{NAME}-purge.json")
        self.lock = self.root / "run" / (NAME + ".lock")
        self.parents = [self.root / part for part in ("opt", "etc", "var", "var/lib", "var/cache", "run")]
        for path in self.parents:
            safe_dir(path)
        self.directories = {
            self.code: 0o755, self.releases: 0o755, self.config: 0o700,
            self.config / "overlay": 0o700, self.data: 0o700, self.cache: 0o700,
            **{self.data / name: 0o700 for name in (
                "state", "journal", "board", "audit", "hq", "vault", "evidence",
                "credentials", "projects", "backups", "control"
            )},
            self.data / "state/migrations": 0o700,
        }
        for path in self.directories:
            safe_dir(path)

    @staticmethod
    def filesystem(path):
        return subprocess.check_output(
            ["/usr/bin/findmnt", "-n", "-o", "FSTYPE", "-T", str(path)], text=True
        ).strip()

    def make_directory(self, path, mode):
        if safe_dir(path) is None:
            if self.fs == "btrfs" and path in {self.config, self.data}:
                require(shutil.which("btrfs"), "Install btrfs-progs before using the btrfs base")
                subprocess.run(["/usr/bin/btrfs", "subvolume", "create", str(path)], check=True)
            else:
                path.mkdir(mode=mode)
            sync_dir(path.parent)
        path.chmod(mode)

    def recovery(self):
        return read_json(self.control / "transaction.json") or read_json(self.purge_record)

    def record(self):
        return read_json(self.control / "install.json", {"highest": None, "previous": None})


def current(paths):
    if not paths.current.exists() and not paths.current.is_symlink():
        return None
    require(paths.current.is_symlink(), "Refusing to replace an unmanaged current path")
    target = os.readlink(paths.current)
    require(target.startswith("releases/"), "Unexpected current link")
    version = target.removeprefix("releases/")
    version_key(version)
    require(safe_dir(paths.releases / version), "Current release directory is missing")
    return version


def point(paths, version):
    if version is None:
        paths.current.unlink(missing_ok=True)
    else:
        temp = paths.code / ".current-next"
        temp.unlink(missing_ok=True)
        temp.symlink_to(f"releases/{version}")
        temp.replace(paths.current)
    sync_dir(paths.code)


def choices(paths, overlay=None):
    overlay = overlay or paths.config / "overlay"
    if overlay != paths.config / "overlay":
        require(not overlay.is_symlink() and overlay.is_dir(), "Overlay must be a directory")
    source = overlay / "installer.json"
    mode = file_mode(source)
    raw = source.read_bytes() if mode is not None else b"{}"
    config = json.loads(raw)
    require(isinstance(config, dict) and config.keys() <= {"snapshot_free_percent"},
            "Unknown installer overlay choice")
    floor = config.get("snapshot_free_percent", 20)
    require(type(floor) is int and 20 <= floor <= 90, "Snapshot free-space floor must be 20–90 percent")
    return floor, digest(raw), raw if mode is not None else None


def mode_for(name):
    return 0o555 if name in EXECUTABLES else 0o444


def manifest(release):
    return {"archive": release.checksum, "files": {
        name: {"mode": mode_for(name), "sha256": digest(data)}
        for name, data in sorted(release.files.items())
    }}


def installed_manifest(directory):
    return read_json(directory / ".ownership.json")


def installed_files(directory):
    return {str(path.relative_to(directory)) for path in directory.rglob("*")
            if not path.is_dir() or path.is_symlink()}


def check_release(directory, release=None):
    require(safe_dir(directory), "Release directory is missing")
    value = installed_manifest(directory)
    require(value and (release is None or value == manifest(release)), "Release ownership or checksum mismatch")
    require(installed_files(directory) == {".ownership.json", *value["files"]},
            "Unexpected or missing release files")
    expected_dirs = {str(parent) for name in value["files"] for parent in Path(name).parents
                     if parent != Path(".")}
    actual_dirs = {str(path.relative_to(directory)) for path in directory.rglob("*")
                   if path.is_dir() and not path.is_symlink()}
    require(expected_dirs == actual_dirs, "Unexpected release directories")
    require(stat.S_IMODE(directory.stat().st_mode) == 0o555
            and file_mode(directory / ".ownership.json") == 0o444
            and all(stat.S_IMODE(safe_dir(directory / name).st_mode) == 0o555
                    for name in actual_dirs), "Release directory permissions drifted")
    for name, item in value["files"].items():
        require(file_mode(directory / name) == item["mode"]
                and digest((directory / name).read_bytes()) == item["sha256"],
                f"Installed release drift: {name}")
    return value


def retained_data(paths):
    # An interrupted fresh install can leave empty layout directories and a signer pin.
    # Everything else under the state tree, including migration markers, is retained data.
    def has_data(directory):
        return directory.is_dir() and any(
            entry != paths.signers and (entry not in paths.directories or has_data(entry))
            for entry in directory.iterdir()
        )

    return has_data(paths.data)


def describe(paths, operation, release=None, *, overlay=None, channel_digest=None, signer=None, purge=False):
    require(not paths.recovery(), "Interrupted change: run recover first")
    before = current(paths)
    record = paths.record()
    floor, overlay_digest, overlay_bytes = choices(paths, overlay)
    result = {
        "schema": 1, "operation": operation, "current": before, "record": record,
        "filesystem": paths.fs, "overlay": overlay_digest, "changes": [],
        "packages": [], "users": [], "units": [], "firewall": [], "incus": [],
    }
    changes = result["changes"]
    if operation in {"install", "update"}:
        require(not paths.retired.exists(), "Interrupted uninstall: finish uninstall first")
        version = release.version
        result.update(release=version, archive=release.checksum, channel=channel_digest, signer=signer)
        if file_mode(paths.signers) is None:
            changes.append({"action": "pin-release-signer", "fingerprint": signer})
        if before:
            check_release(paths.releases / before)
        if record["highest"]:
            highest = record["highest"]
            require(version != highest or record.get("highest_archive", release.checksum) == release.checksum,
                    "Release bytes differ from the highest installed version")
            require(version_key(version) >= version_key(highest)
                    and (version_key(version) != version_key(highest) or version == highest),
                    "Only rollback can go below the highest installed release")
        require(operation != "update" or before, "Update requires an existing installation")
        require(operation != "install" or before in {None, version}, "Use update to change releases")
        for path, mode in paths.directories.items():
            info = safe_dir(path)
            if info is None or stat.S_IMODE(info.st_mode) != mode:
                changes.append({"action": "ensure-subvolume" if paths.fs == "btrfs"
                                and path in {paths.config, paths.data} else "ensure-directory",
                                "path": "/" + str(path.relative_to(paths.root)), "mode": oct(mode)})
            if paths.fs == "btrfs" and info and path in {paths.config, paths.data}:
                require(info.st_ino == 256, f"Expected a product subvolume at {path}")
        if overlay is not None and overlay_bytes is not None and (choices(paths)[2] is None or choices(paths)[1] != overlay_digest):
            changes.append({"action": "write-overlay-choice", "path": f"/etc/{NAME}/overlay/installer.json",
                            "snapshot_free_percent": floor})
        directory = paths.releases / version
        if safe_dir(directory):
            check_release(directory, release)
        else:
            for name, data in sorted(release.files.items()):
                lines = data.decode("utf-8").splitlines(keepends=True)
                diff = "".join(difflib.unified_diff([], lines, fromfile="/dev/null", tofile=name))
                changes.append({"action": "install-file", "path": f"/opt/{NAME}/releases/{version}/{name}",
                                "sha256": digest(data), "mode": oct(mode_for(name)), "diff": diff})
            changes.append({"action": "write-ownership-manifest", "release": version})
        pending = migrations(paths, release.files)
        if before != version:
            fresh = not before and not record["highest"] and not retained_data(paths)
            if before or (pending and not fresh) or any(change["action"] == "write-overlay-choice" for change in changes):
                changes.append({"action": "snapshot" if paths.fs == "btrfs" else "export",
                                "free_percent": floor})
            changes.extend({"action": "mark-baseline" if fresh else "migrate", "epoch": epoch} for epoch in pending)
            changes.append({"action": "activate", "release": version})
        else:
            require(not pending, "Current release has missing migration markers")
    elif operation == "rollback":
        previous = record["previous"]
        require(before and previous, "No previous release checkpoint")
        check_release(paths.releases / before)
        check_release(paths.releases / previous["version"])
        require((paths.data / "backups" / previous["backup"]).is_dir(), "Rollback checkpoint is missing")
        changes.append({"action": "restore", **previous})
    elif operation == "uninstall":
        if safe_dir(paths.retired):
            changes.append({"action": "finish-owned-code-removal"})
        if safe_dir(paths.code):
            require({child.name for child in paths.code.iterdir()} <= {"current", "releases"},
                    "Unmanaged content in the code directory")
            versions = []
            if safe_dir(paths.releases):
                for directory in sorted(paths.releases.iterdir()):
                    if directory.name == ".staging":
                        require(safe_dir(directory), "Invalid interrupted staging directory")
                        continue
                    version_key(directory.name)
                    owned = check_release(directory)
                    versions.append({"version": directory.name, **owned})
            changes.append({"action": "remove-owned-code", "releases": versions})
        if not purge and record["previous"]:
            changes.append({"action": "clear-rollback-pointer"})
        if purge and (paths.data.exists() or paths.config.exists()):
            require(paths.data.is_dir() and paths.config.is_dir(), "Purge requires both product trees")
            require(not any((paths.data / "projects").iterdir()),
                    "Project data exists; preserve and retire projects before purge")
            backup.verify_tree(paths.config, set(), btrfs=paths.fs == "btrfs")
            backup.verify_tree(paths.data, {"backups", "credentials", "control"}, btrfs=paths.fs == "btrfs")
            changes.append({"action": "checkpoint-and-purge", "free_percent": floor})
    return result


def migrations(paths, names):
    return sorted(Path(name).stem for name in names if re.fullmatch(r"migrations/[0-9]{10}\.py", name)
                  and not (paths.data / "state/migrations" / Path(name).stem).is_file())


def stage_release(paths, release):
    directory = paths.releases / release.version
    if directory.exists():
        return
    stage = paths.releases / ".staging"
    if safe_dir(stage):
        remove_retired(stage)
    stage.mkdir(mode=0o755)
    try:
        for name, data in sorted(release.files.items()):
            file = stage / name
            file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(file, data, mode_for(name))
        atomic_write(stage / ".ownership.json", encode(manifest(release)), 0o444)
        nested = sorted((path for path in stage.rglob("*") if path.is_dir()),
                        key=lambda path: len(path.parts), reverse=True)
        for folder in [*nested, stage]:
            folder.chmod(0o555)
            sync_dir(folder)
        stage.rename(directory)
        sync_dir(paths.releases)
    finally:
        if stage.exists():
            remove_retired(stage)


def save(paths, value):
    atomic_write(paths.control / "install.json", encode(value))


def journal_transaction(paths, value):
    atomic_write(paths.control / "transaction.json", encode(value))


def finish(paths):
    (paths.control / "transaction.json").unlink()
    sync_dir(paths.control)


def recover(paths):
    backup.clean_legacy_stages(paths)
    tx = paths.recovery()
    if not tx:
        return
    if "purge" in tx:
        finish_purge(paths, tx["purge"], tx.get("floor", 20), legacy="floor" not in tx)
        return
    if tx["backup"]:
        backup.restore(paths, tx["backup"])
    elif not tx["current"]:
        for epoch in tx.get("baseline", []):
            (paths.data / "state/migrations" / epoch).unlink(missing_ok=True)
    point(paths, tx["current"])
    save(paths, tx["record"])
    finish(paths)


def health(directory):
    subprocess.run([str(directory / NAME), "self-check"], check=True, timeout=30)


def activate(paths, plan, release, *, overlay, signers):
    for parent in paths.parents:
        if not parent.exists():
            parent.mkdir()
    for path, mode in paths.directories.items():
        info = safe_dir(path)
        if info is None or stat.S_IMODE(info.st_mode) != mode:
            paths.make_directory(path, mode)
    if file_mode(paths.signers) is None:
        atomic_write(paths.signers, signers)
    def write_overlay():
        if any(change["action"] == "write-overlay-choice" for change in plan["changes"]):
            _, checksum, raw = choices(paths, overlay)
            require(checksum == plan["overlay"], "Overlay changed during apply")
            atomic_write(paths.config / "overlay/installer.json", raw)

    if plan["current"] == release.version:
        write_overlay()
        return
    stage_release(paths, release)
    directory = paths.releases / release.version
    checkpoint = next((change for change in plan["changes"]
                       if change["action"] in {"snapshot", "export"}), None)
    previous = plan["record"]["previous"]
    backup.prune(paths, [previous["backup"]] if previous else [])
    identifier = backup.create(paths, checkpoint["free_percent"]) if checkpoint else None
    journal_transaction(paths, {"current": plan["current"], "backup": identifier,
                                "record": plan["record"], "baseline": [change["epoch"] for change in plan["changes"]
                                    if change["action"] == "mark-baseline"]})
    try:
        write_overlay()
        for change in plan["changes"]:
            if change["action"] == "migrate":
                require(identifier, "Refusing to migrate without a checkpoint")
                epoch = change["epoch"]
                subprocess.run([sys.executable, "-I", "-B", str(directory / f"migrations/{epoch}.py"),
                                str(paths.config), str(paths.data)], check=True, timeout=300)
            if change["action"] in {"migrate", "mark-baseline"}:
                marker = b"baseline\n" if change["action"] == "mark-baseline" else b"applied\n"
                atomic_write(paths.data / "state/migrations" / change["epoch"], marker)
        health(directory)
        point(paths, release.version)
        save(paths, {"highest": release.version, "highest_archive": release.checksum, "previous": (
            {"version": plan["current"], "backup": identifier} if plan["current"] else None
        )})
        finish(paths)
    except BaseException:
        recover(paths)
        raise
    backup.prune(paths, [identifier] if identifier else [])


def rollback(paths, plan):
    previous = plan["record"]["previous"]
    health(paths.releases / previous["version"])
    floor, _, _ = choices(paths)
    backup.prune(paths, [previous["backup"]])
    undo = backup.create(paths, floor)
    journal_transaction(paths, {"current": plan["current"], "backup": undo,
                                "record": plan["record"]})
    try:
        backup.restore(paths, previous["backup"])
        point(paths, previous["version"])
        save(paths, {**plan["record"], "previous": None})
        finish(paths)
    except BaseException:
        recover(paths)
        raise
    backup.remove(paths, undo)
    backup.prune(paths)


def uninstall(paths, plan, confirmation):
    purge = any(change["action"] == "checkpoint-and-purge" for change in plan["changes"])
    if purge:
        require(confirmation == f"purge {NAME}", f"Purge requires typed confirmation: purge {NAME}")
        for path in (paths.config, paths.data):
            require(not path.with_name(f".{NAME}-purging").exists()
                    and not path.with_name(f".{NAME}-purging").is_symlink(),
                    "Unexpected purge staging directory")
        identifier = uuid.uuid4().hex
        floor = choices(paths)[0]
        atomic_write(paths.purge_record, encode({"purge": identifier, "floor": floor}))
        finish_purge(paths, identifier, floor)
        return
    retire_code(paths)
    if paths.control.exists():
        record = paths.record()
        record["previous"] = None
        save(paths, record)


def retire_code(paths):
    if paths.retired.exists():
        remove_retired(paths.retired)
    if paths.code.exists():
        paths.code.rename(paths.retired)
        sync_dir(paths.code.parent)
        remove_retired(paths.retired)


def finish_purge(paths, identifier, floor, *, legacy=False):
    backup.clean_legacy_stages(paths)
    kept = backup.final_export(paths, identifier, floor, legacy=legacy)
    print(f"Final checkpoint retained at {kept}")
    print(f"To discard the checkpoint, run as owner: rm -r -- {kept}")
    audit_file = paths.data / "audit/events.jsonl"
    if file_mode(audit_file) is not None and not paths.test:
        backup.run("/usr/bin/chattr", "-a", "--", str(audit_file))
    for path in (paths.config, paths.data):
        staging = path.with_name(f".{NAME}-purging")
        if safe_dir(path):
            require(not safe_dir(staging), "Conflicting purge staging directory")
            path.rename(staging)
            sync_dir(path.parent)
        if safe_dir(staging):
            if paths.fs == "btrfs":
                if path == paths.data:
                    for child in (staging / "backups").iterdir():
                        backup.remove_tree(child, True)
                backup.run("/usr/bin/btrfs", "subvolume", "delete", str(staging))
            else:
                shutil.rmtree(staging)
            sync_dir(staging.parent)
    retire_code(paths)
    paths.purge_record.unlink()
    sync_dir(paths.purge_record.parent)


def remove_retired(directory):
    for folder, _, _ in os.walk(directory):
        Path(folder).chmod(0o700)
    shutil.rmtree(directory)
    sync_dir(directory.parent)
