# SPDX-License-Identifier: MIT
"""Inventory persistent guest files and installed packages via an offline VM."""

import gzip
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from initramfs import fingerprint

EMPTY = hashlib.sha256(b"").hexdigest()
UUID = re.compile(rb"(?m)^(\s*UUID=)(?:[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}|[a-fA-F0-9]{4}-[a-fA-F0-9]{4})(?=[ \t])")
SCRUBBED = {"/var/lib/snapd/state.json", "/var/lib/snapd/state.json.bak", "/var/lib/snapd/state.json.old",
            "/var/lib/systemd/random-seed", "/var/cache/ldconfig/aux-cache", "/var/log/journal"}


def record(path):
    info = path.lstat()
    mode = info.st_mode
    row = {"mode": stat.S_IMODE(mode), "uid": info.st_uid, "gid": info.st_gid,
           "size": 0, "sha256": EMPTY,
           "xattrs": {name: hashlib.sha256(os.getxattr(path, name, follow_symlinks=False)).hexdigest()
                      for name in sorted(os.listxattr(path, follow_symlinks=False))}}
    if stat.S_ISREG(mode):
        row.update(type="file", size=info.st_size)
        with path.open("rb") as stream:
            row["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    elif stat.S_ISDIR(mode):
        row["type"] = "directory"
    elif stat.S_ISLNK(mode):
        target = os.fsencode(path.readlink())
        row.update(type="symlink", size=len(target), sha256=hashlib.sha256(target).hexdigest())
    else:
        kinds = {stat.S_IFBLK: "block", stat.S_IFCHR: "character", stat.S_IFIFO: "fifo", stat.S_IFSOCK: "socket"}
        row.update(type=kinds[stat.S_IFMT(mode)], sha256=hashlib.sha256(str(info.st_rdev).encode()).hexdigest())
    return row


def inventory(root, normalize_initramfs=False):
    entries = {"/": record(root)}
    directories = [root]
    while directories:
        directory = directories.pop()
        for path in directory.iterdir():
            name = "/" + path.relative_to(root).as_posix()
            row = entries[name] = record(path)
            if row["type"] == "directory":
                directories.append(path)
            if name == "/etc/fstab" and row["type"] == "file":
                row["uuid_normalized_sha256"] = hashlib.sha256(
                    UUID.sub(rb"\g<1><uuid>", path.read_bytes())).hexdigest()
            if normalize_initramfs and re.fullmatch(r"/boot/initrd\.img-[^/]+", name) and row["type"] == "file":
                row["initramfs_normalized_sha256"] = fingerprint(path)
    return entries


def installed(root):
    results = subprocess.check_output(
        ["/usr/bin/dpkg-query", f"--admindir={root / 'var/lib/dpkg'}", "-W",
         "-f", "${db:Status-Status}\t${Package}\t${Architecture}\t${Version}\n"], text=True,
    )
    packages = {}
    for line in results.splitlines():
        status, package, architecture, version = line.split("\t")
        if status == "installed":
            key = f"{package}:{architecture}"
            if key in packages or not version:
                raise SystemExit("Invalid installed package record")
            packages[key] = version
    if not packages:
        raise SystemExit("Installed package list is empty")
    return packages


def require_clean(device, filesystem):
    if filesystem == "ext4":
        details = subprocess.check_output(["dumpe2fs", "-h", device], text=True)
        features = re.findall(r"^Filesystem features:[ \t]+(.+)$", details, re.MULTILINE)
        states = re.findall(r"^Filesystem state:[ \t]+(.+)$", details, re.MULTILINE)
        if len(features) != 1 or "needs_recovery" in features[0].split() or states != ["clean"]:
            raise SystemExit(f"Ext4 filesystem is dirty or needs journal replay: {device}")
    elif filesystem == "btrfs":
        details = subprocess.check_output(["btrfs", "inspect-internal", "dump-super", "-a", device], text=True)
        mirrors = re.findall(r"^superblock:", details, re.MULTILINE)
        logs = re.findall(r"^log_root[ \t]+(\d+)$", details, re.MULTILINE)
        checksums = re.findall(r"^csum[ \t]+.+\[match\]$", details, re.MULTILINE)
        if not mirrors or len(checksums) != len(mirrors) or logs != ["0"] * len(mirrors):
            raise SystemExit(f"Btrfs filesystem has an invalid superblock or a pending tree log: {device}")


def require_readonly(device):
    if subprocess.check_output(["blockdev", "--getro", device], text=True).strip() != "1":
        raise SystemExit("Inventory disks must be presented read-only")


def partition_digest(device):
    with open(device, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(role, device, canonical_bios=None):
    # Mount each filesystem separately so a boot mount cannot hide files on root.
    layout = ({"root": (2, "btrfs", "nologreplay"), "efi": (1, "vfat", "fmask=0177,dmask=0077")}
              if role == "btrfs" else
              {"root": (1, "ext4", "noload"), "boot": (16, "ext4", "noload"),
               "efi": (15, "vfat", "fmask=0177,dmask=0077")})
    require_readonly(device)
    declared = {f"{device}{number}": filesystem for number, filesystem, _ in layout.values()}
    if role != "btrfs":
        declared[f"{device}14"] = None  # The Canonical BIOS boot partition has no filesystem.
    tree = json.loads(subprocess.check_output(["lsblk", "-Jpo", "NAME,FSTYPE", device], text=True))["blockdevices"]
    actual = {row["name"]: row["fstype"] for row in tree[0].get("children", [])}
    if actual != declared:
        raise SystemExit(f"Unexpected partition or filesystem layout for {role}")
    if role != "btrfs":
        if partition_digest(f"{device}14") != canonical_bios:
            raise SystemExit(f"BIOS boot partition differs from the verified Canonical image for {role}")
        print(f"FIXTURE CANONICAL BIOS PARTITION VERIFIED {role} {canonical_bios}", flush=True)
    partitions = {}
    with ExitStack() as cleanup:
        for name, (number, filesystem, options) in layout.items():
            partition = f"{device}{number}"
            require_clean(partition, filesystem)
            mount = Path("/run/fixture-manifest") / name
            mount.mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", "-t", filesystem, "-o", f"ro,noexec,nosuid,nodev,{options}",
                            partition, str(mount)], check=True)
            cleanup.callback(subprocess.run, ["umount", str(mount)], check=True)
            partitions[name] = inventory(mount, normalize_initramfs=role == "btrfs" and name == "root")
            print(f"FIXTURE INVENTORIED {role} {name} ({len(partitions[name])} entries)", flush=True)
            if name == "root":
                leftovers = SCRUBBED & partitions[name].keys()
                if leftovers:
                    raise SystemExit(f"Unexpected build state in {role}: {', '.join(sorted(leftovers))}")
                packages = installed(mount)
    return {"schema": 1, "role": role, "partitions": partitions, "packages": packages}


def main(roles):
    os.environ["LC_ALL"] = "C"
    subprocess.run(["udevadm", "settle", "--timeout=30"], check=True)
    disks = json.loads(subprocess.check_output(["lsblk", "-dJpo", "PATH,SERIAL"], text=True))["blockdevices"]

    def disk_for(role):
        matches = [disk["path"] for disk in disks if disk["serial"] == f"fixture-{role}"]
        if len(matches) != 1:
            raise SystemExit(f"Expected one read-only fixture device for {role}")
        return matches[0]

    canonical_bios = None
    if set(roles) & {"ext4", "worker"}:
        canonical = disk_for("canonical")
        require_readonly(canonical)
        canonical_bios = partition_digest(f"{canonical}14")
    for role in roles:
        data = collect(role, disk_for(role), canonical_bios)
        # The virtio character device can return partial writes. BufferedWriter
        # completes them before the gzip stream is closed.
        with (open(f"/dev/virtio-ports/manifest-{role}", "wb") as channel,
              gzip.GzipFile(fileobj=channel, mode="wb", filename="", mtime=0) as compressed):
            compressed.write(json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        print(f"FIXTURE MANIFEST EXPORTED {role}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
