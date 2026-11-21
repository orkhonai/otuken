# SPDX-License-Identifier: MIT
"""Compare guest-exported inventories under the reviewed fixture allowlist."""

import gzip
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

ROLES = ("btrfs", "ext4", "worker")
PARTITIONS = {"btrfs": {"root", "efi"}, "ext4": {"root", "boot", "efi"}, "worker": {"root", "boot", "efi"}}
MAX_COMPRESSED = 32 * 1024**2
MAX_EXPANDED = 128 * 1024**2
HEX = re.compile(r"[0-9a-f]{64}")
KINDS = {"file", "directory", "symlink", "block", "character", "fifo", "socket"}
FIELDS = {"type", "mode", "uid", "gid", "size", "sha256", "xattrs"}
NORMALIZED = {"uuid_normalized_sha256", "initramfs_normalized_sha256"}
PAYLOAD = {"size", "sha256"} | NORMALIZED


def require(check, message):
    if not check:
        raise SystemExit(message)


def allowlist():
    return json.loads(Path(__file__).with_name("fixture-allowlist.json").read_text())


def unique_object(pairs):
    result = dict(pairs)
    require(len(result) == len(pairs), "Duplicate key in guest inventory")
    return result


def load(path, role):
    with path.open("rb") as stream:
        compressed = stream.read(MAX_COMPRESSED + 1)
    require(0 < len(compressed) <= MAX_COMPRESSED, f"Invalid inventory size for {role}")
    checksum = hashlib.sha256(compressed).hexdigest()
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        data = stream.read(MAX_EXPANDED + 1)
    require(0 < len(data) <= MAX_EXPANDED, f"Invalid expanded inventory size for {role}")
    value = json.loads(data, object_pairs_hook=unique_object)
    require(isinstance(value, dict) and value.get("schema") == 1 and value.get("role") == role,
            f"Invalid guest inventory for {role}")
    partitions = value.get("partitions")
    require(isinstance(partitions, dict) and partitions.keys() == PARTITIONS[role], f"Unexpected partitions for {role}")
    for name, entries in partitions.items():
        validate_entries(entries, role, name)
    packages = value.get("packages")
    require(isinstance(packages, dict) and packages and
            all(package and isinstance(version, str) and version for package, version in packages.items()),
            f"Invalid installed packages for {role}")
    return value, checksum


def validate_entries(entries, role, partition):
    require(isinstance(entries, dict) and isinstance(entries.get("/"), dict)
            and entries["/"].get("type") == "directory", f"Missing root in {role} {partition}")
    for path, row in entries.items():
        subject = f"{role} {partition} {path!a}"
        require(path.startswith("/") and (path == "/" or all(part not in {"", ".", ".."} for part in path[1:].split("/"))),
                f"Invalid inventory path in {subject}")
        require(isinstance(row, dict) and FIELDS <= row.keys() <= FIELDS | NORMALIZED
                and row["type"] in KINDS, f"Invalid inventory record in {subject}")
        if path != "/":
            require(entries.get(path.rpartition("/")[0] or "/", {}).get("type") == "directory",
                    f"Missing inventory parent in {subject}")
        require(all(type(row[key]) is int and row[key] >= 0 for key in ("mode", "uid", "gid", "size"))
                and row["mode"] <= 0o7777 and isinstance(row["sha256"], str) and HEX.fullmatch(row["sha256"])
                and isinstance(row["xattrs"], dict)
                and all(isinstance(checksum, str) and HEX.fullmatch(checksum) for checksum in row["xattrs"].values()),
                f"Invalid inventory metadata in {subject}")
        normalized = row.get("uuid_normalized_sha256")
        if normalized is not None:
            require(path == "/etc/fstab" and partition == "root" and row["type"] == "file"
                    and isinstance(normalized, str) and HEX.fullmatch(normalized), f"Unexpected normalized digest in {subject}")
        if "initramfs_normalized_sha256" in row:
            value = row["initramfs_normalized_sha256"]
            require(role == "btrfs" and partition == "root" and re.fullmatch(r"/boot/initrd\.img-[^/]+", path)
                    and row["type"] == "file" and isinstance(value, str) and HEX.fullmatch(value),
                    f"Unexpected initramfs digest in {subject}")


def metadata(row):
    return {key: value for key, value in row.items() if key not in PAYLOAD}


def allowed(rule, path, prior, current):
    kind = rule["rule"]
    if kind == "logs":
        if (not path.startswith(rule["path"] + "/") or path == "/var/log/journal"
                or path.startswith("/var/log/journal/")):
            return False
        # A log exception cannot introduce executable files, special files or links.
        if prior is None or current is None:
            row = prior if current is None else current
            return (not row["xattrs"] and
                    (row["type"] == "file" and not row["mode"] & 0o7111 or
                     row["type"] == "directory" and not row["mode"] & 0o7022))
    elif path != rule["path"]:
        return False
    if prior is None or current is None or prior["type"] != "file" or metadata(prior) != metadata(current):
        return False
    if kind == "logs":
        return not prior["mode"] & 0o7111
    if kind == "fstab-uuid":
        return ("uuid_normalized_sha256" in prior and
                prior["uuid_normalized_sha256"] == current.get("uuid_normalized_sha256"))
    if kind == "initramfs":
        return ("initramfs_normalized_sha256" in prior and
                prior["initramfs_normalized_sha256"] == current.get("initramfs_normalized_sha256"))
    return kind == "content"


def compare(role, reference, cold, rules):
    unexpected = []
    exceptions = Counter()
    for package in sorted(reference["packages"].keys() | cold["packages"].keys()):
        if reference["packages"].get(package) != cold["packages"].get(package):
            unexpected.append(f"{role} installed package {package!a}")
    for partition, before in reference["partitions"].items():
        after = cold["partitions"][partition]
        eligible = [rule for rule in rules if rule["partition"] == partition and rule.get("role", role) == role]
        for path in sorted(before.keys() | after.keys()):
            a, b = before.get(path), after.get(path)
            if a == b:
                continue
            match = next((rule for rule in eligible if allowed(rule, path, a, b)), None)
            if match:
                exceptions[f"{role}:{partition}:{match['path']}"] += 1
            else:
                unexpected.append(f"{role} {partition} {path!a}")
    return unexpected, exceptions


def evidence(agent_paths, cold_paths, expected):
    rules = allowlist()
    all_exceptions = Counter()
    checksums = {"agent": {}, "cold": {}}
    for role in ROLES:
        agent, checksum = load(agent_paths[role], role)
        require(checksum == expected[role], f"Reviewed agent inventory changed for {role}")
        cold, cold_checksum = load(cold_paths[role], role)
        differences, exceptions = compare(role, agent, cold, rules)
        require(not differences, f"Guest inventory mismatch ({len(differences)})\n" + "\n".join(differences[:30]))
        all_exceptions.update(exceptions)
        checksums["agent"][role] = {"file": f"evidence/agent.{role}.json.gz", "sha256": checksum}
        checksums["cold"][role] = {"file": f"evidence/cold.{role}.json.gz", "sha256": cold_checksum}
    return {**checksums, "authoritative": "cold", "allowlist": rules,
            "comparison": {"status": "passed", "allowed_differences": dict(sorted(all_exceptions.items()))}}
