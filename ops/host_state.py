# SPDX-License-Identifier: MIT
"""Record and reverse only the host changes attributable to the Incus CI install."""

import grp
import json
import os
import pwd
import re
import subprocess
import sys
import time
from glob import escape
from pathlib import Path, PurePosixPath

ACCOUNTS = ("incus",)
GROUPS = ("incus", "incus-admin")
SUBIDS = ("subuid", "subgid")
LOCAL_FILESYSTEMS = {"btrfs", "ext2", "ext3", "ext4", "f2fs", "xfs", "zfs"}
VIRTUAL_PATHS = ("/proc", "/sys", "/dev")
SCAN_TIMEOUT = 90
MODULES = {"vhost_vsock", "vhost", "vhost_iotlb", "vsock", "vsock_loopback",
           "vmw_vsock_virtio_transport_common", "tun", "fuse", "kvm", "kvm_intel", "kvm_amd"}


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def output(*args):
    return subprocess.check_output(args, text=True)


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def get_all(getter, names):
    rows = {}
    for name in names:
        try:
            rows[name] = list(getter(name))
        except KeyError:
            pass
    return rows


def subid_files():
    values = {}
    for name in SUBIDS:
        path = Path("/etc") / name
        if path.exists():
            info = path.stat()
            values[name] = {"text": path.read_text(), "mode": info.st_mode & 0o777,
                            "uid": info.st_uid, "gid": info.st_gid}
    return values


def packages():
    listing = output("/usr/bin/dpkg-query", "-W", "-f=${db:Status-Abbrev}\t${binary:Package}\t${Version}\n")
    return {name: [status.strip(), version] for status, name, version in
            (line.split("\t") for line in listing.splitlines())}


def modules():
    return {fields[0]: int(fields[2]) for fields in
            (line.split() for line in Path("/proc/modules").read_text().splitlines())}


def capture():
    return {"packages": packages(), "auto": sorted(output("/usr/bin/apt-mark", "showauto").splitlines()),
            "users": get_all(pwd.getpwnam, ACCOUNTS), "groups": get_all(grp.getgrnam, GROUPS),
            "subids": subid_files(), "modules": sorted(modules())}


def write_snapshot(path):
    with path.open("w") as stream:
        json.dump(capture(), stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def apt_rows(plan, verbs):
    return [parts[1] for line in plan.splitlines() if (parts := line.split()) and parts[0] in verbs]


def canonical(names, reported):
    resolved = set()
    for item in reported:
        matches = [name for name in names if name == item or name.split(":")[0] == item]
        require(len(matches) == 1, f"Ambiguous or unexpected package in apt simulation: {item}")
        resolved.add(matches[0])
    return resolved


def verify_install_plan(before, plan):
    require(not apt_rows(plan, {"Remv", "Purg"}), "APT planned a removal")
    old = {name.split(":")[0] for name in before["packages"]}
    for name in apt_rows(plan, {"Inst"}):
        require(name.split(":")[0] not in old, f"APT would change an existing package record: {name}")


def additions(before, after, plan):
    delta = after["packages"].keys() - before["packages"].keys()
    offered = set(apt_rows(plan, {"Inst"}))
    return sorted(name for name in delta if name in offered or name.split(":")[0] in offered)


def verify_purge_plan(before, after, install_plan, plan):
    allowed = additions(before, after, install_plan)
    remaining = [key for key in allowed if key in packages()]
    require(not apt_rows(plan, {"Inst"}), "Purge would install or upgrade packages")
    require(canonical(remaining, apt_rows(plan, {"Remv", "Purg"})) == set(remaining),
            "Purge does not match the recorded package delta")


def subid_delta(before, after, name):
    original = before["subids"].get(name, {}).get("text", "").splitlines()
    installed = after["subids"].get(name, {}).get("text", "").splitlines()
    return sorted(row for row in set(installed) - set(original) if re.fullmatch(r"root:\d+:[1-9]\d*", row))


def restore_subids(before, after):
    for name in SUBIDS:
        path = Path("/etc") / name
        for row in subid_delta(before, after, name):
            if path.exists() and row in path.read_text().splitlines():
                first, count = map(int, row.split(":")[1:])
                run("/usr/sbin/usermod", "--del-" + name + "s", f"{first}-{first + count - 1}", "root")
        if (name not in before["subids"] and name in after["subids"]
                and path.exists() and path.stat().st_size == 0):
            path.unlink()


def snapshot_name(name):
    return name in {".snapshot", ".snapshots", ".zfs"} or (name.startswith(".") and name.endswith("-snapshots"))


def disjunction(terms):
    return [word for index, term in enumerate(terms) for word in (("-o", *term) if index else term)]


def skipped_mounts(mounts):
    return {*VIRTUAL_PATHS, *(row["target"] for row in mounts if row["fstype"] not in LOCAL_FILESYSTEMS)}


def excluded(target, skipped):
    return (any(target == path or target.startswith(path + "/") for path in skipped)
            or any(snapshot_name(part) for part in Path(target).parts))


def subvolume_targets(mount, listing):
    relative_root = PurePosixPath(mount["fsroot"].lstrip("/"))
    for line in listing.splitlines():
        match = re.fullmatch(r"ID \d+ .* path (.+)", line)
        require(match, "Unexpected btrfs subvolume listing")
        raw = match[1].removeprefix("<FS_TREE>/")
        location = PurePosixPath(raw)
        require(not location.is_absolute() and ".." not in location.parts, "Unsafe btrfs subvolume path")
        if location.is_relative_to(relative_root):
            yield str(Path(mount["target"]) / location.relative_to(relative_root))


def ownership_command(mounts, users, groups, subvolumes=()):
    skipped = skipped_mounts(mounts)
    roots = sorted({row["target"] for row in mounts
                    if row["fstype"] in LOCAL_FILESYSTEMS and not excluded(row["target"], skipped)} | {path for path in subvolumes if not excluded(path, skipped)})
    require(roots and "/" in roots, "Cannot establish the local root filesystem for ownership checks")
    paths = [("-path", escape(path)) for path in sorted(skipped)]
    snapshots = [("-name", name) for name in (".snapshot", ".snapshots", ".*-snapshots", ".zfs")]
    identities = [(f"-{kind}", str(value)) for kind, values in (("uid", users), ("gid", groups))
                  for value in sorted(values)]
    return ["/usr/bin/ionice", "-c", "3", "/usr/bin/nice", "-n", "19", "/usr/bin/find", *roots,
            "-xdev", "(", *disjunction(paths + snapshots), ")", "-prune", "-o",
            "(", *disjunction(identities), ")", "-print", "-quit"]


def check_id_ownership(users, groups):
    if not (users or groups):
        return
    lines = output("/usr/bin/ps", "-e", "-o", "ruid=,euid=,rgid=,egid=,supgid=").splitlines()
    for line in lines:
        identity = line.split()
        gids = set(map(int, identity[2:4]))
        if len(identity) > 4:
            gids.update(int(value) for value in identity[4].split(",") if value.isdecimal())
        require(not (users & set(map(int, identity[:2])) or groups & gids),
                "An Incus ID is still used by processes")
    try:
        seconds = int(os.environ.get("OTUKEN_CI_OWNERSHIP_SCAN_SECONDS", SCAN_TIMEOUT))
    except ValueError:
        raise SystemExit("Invalid ownership scan timeout") from None
    require(1 <= seconds <= 1800, "Ownership scan timeout must be 1–1800 seconds")
    deadline = time.monotonic() + seconds

    def read(*args):
        return subprocess.check_output(args, text=True, timeout=max(0.001, deadline - time.monotonic()))

    try:
        mounts = json.loads(read("/usr/bin/findmnt", "--json", "--list", "-o", "TARGET,FSTYPE,FSROOT"))["filesystems"]
        skipped = skipped_mounts(mounts)
        nested = set()
        for mount in mounts:
            if mount["fstype"] == "btrfs" and not excluded(mount["target"], skipped):
                listing = read("/usr/bin/ionice", "-c", "3", "/usr/bin/nice", "-n", "19",
                               "/usr/bin/btrfs", "subvolume", "list", "-a", mount["target"])
                nested.update(subvolume_targets(mount, listing))
        found = read(*ownership_command(mounts, users, groups, nested))
    except subprocess.TimeoutExpired:
        raise SystemExit("Local ownership scan exceeded its time limit; Incus identities were retained") from None
    require(not found, "Incus IDs still own host files; check from the maintenance console")


def restore_identities(before, after):
    now = capture()
    users, groups = {}, {}
    for label, target in (("users", users), ("groups", groups)):
        for name, row in after[label].items():
            if name in before[label] or name not in now[label]:
                continue
            require(now[label][name] == row, f"Incus {label} entry changed since installation: {name}")
            target[name] = row[2]
    check_id_ownership(set(users.values()), set(groups.values()))
    for name in users:
        run("/usr/sbin/userdel", name)
    for name in groups:
        if name in get_all(grp.getgrnam, (name,)):
            run("/usr/sbin/groupdel", name)


def module_delta(before, after, run_evidence):
    observed = set(after["modules"])
    for report in run_evidence.glob("*/modules"):
        observed.update(set(report.read_text().splitlines()) & MODULES)
    return (observed - set(before["modules"])) & MODULES


def restore_modules(before, after, run_evidence):
    active = modules()
    added = module_delta(before, after, run_evidence) & active.keys()
    while added:
        candidates = sorted(name for name in added if active.get(name, 0) == 0)
        require(candidates, "An Incus module is still in use; rollback remains incomplete")
        for name in candidates:
            if name in modules():
                run("/usr/sbin/rmmod", "--", name)
            added.remove(name)
        active = modules()


def compare(before, installed, reverted, plan, owned_modules):
    residual = []
    unrelated = []
    delta = set(additions(before, installed, plan))
    for name in sorted(delta & reverted["packages"].keys()):
        residual.append(f"package still present: {name}")
    for name, original in before["packages"].items():
        current = reverted["packages"].get(name)
        if original[0].endswith("i") and (current is None or not current[0].endswith("i")):
            residual.append(f"baseline package removed: {name}")
    for kind in ("users", "groups"):
        for name in sorted((installed[kind].keys() - before[kind].keys()) & reverted[kind].keys()):
            residual.append(f"{kind} entry still present: {name}")
    for name in SUBIDS:
        present = set(reverted["subids"].get(name, {}).get("text", "").splitlines())
        for row in present & set(subid_delta(before, installed, name)):
            residual.append(f"{name} range still present: {row}")
    for name in sorted(set(reverted["modules"]) & owned_modules):
        residual.append(f"module still loaded: {name}")
    for field in ("auto", "users", "groups", "subids", "modules"):
        if before[field] != reverted[field]:
            unrelated.append(field)
    before_packages = before["packages"]
    reverted_packages = {name: version for name, version in reverted["packages"].items() if name not in delta}
    if before_packages != reverted_packages:
        unrelated.append("package versions or unrelated package records")
    if unrelated:
        print("Additional baseline differences for review: " + ", ".join(unrelated))
    require(not residual, "Unrestored Incus state: " + "; ".join(residual))


def main():
    command, directory, *args = sys.argv[1:]
    directory = Path(directory)
    if command == "capture":
        write_snapshot(directory / f"{args[0]}.json")
        return
    before = json.loads((directory / "before.json").read_text())
    if command == "check-install":
        verify_install_plan(before, Path(args[0]).read_text())
        return
    installed = directory / "installed.json"
    after = json.loads(installed.read_text()) if installed.exists() else before
    if command == "additions":
        for key in additions(before, after, (directory / "apt-plan").read_text()):
            if key in packages():
                print(key)
    elif command == "check-purge":
        verify_purge_plan(before, after, (directory / "apt-plan").read_text(), Path(args[0]).read_text())
    elif command == "restore-ids":
        restore_subids(before, after)
        restore_identities(before, after)
    elif command == "restore-modules":
        restore_modules(before, json.loads((directory / "provisioned.json").read_text()), directory / "ci-evidence")
    elif command == "compare":
        provisioned = directory / "provisioned.json"
        owned_modules = (module_delta(before, json.loads(provisioned.read_text()), directory / "ci-evidence")
                         if provisioned.exists() else set())
        plan = directory / "apt-plan"
        compare(before, after, json.loads((directory / "reverted.json").read_text()),
                plan.read_text() if plan.exists() else "", owned_modules)
    else:
        raise SystemExit("Unknown host state action")


if __name__ == "__main__":
    main()
