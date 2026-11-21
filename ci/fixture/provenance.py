# SPDX-License-Identifier: MIT
"""Bind dedicated-user fixture builds to the reviewed media and isolation evidence."""

import hashlib
import json
import os
import pwd
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ci.isolation import T4, T5, T6
from ops.first_run_inputs import (
    check_inventoried_media,
    manifest_paths,
    matches_reference,
    package_manifest,
    reference,
)

BOOT_LOGS = {f"{fs}-boot.serial.log": f"FIXTURE BOOT VERIFIED {fs}" for fs in ("ext4", "btrfs")}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def isolation_evidence(path):
    lines = path.read_text(errors="replace").splitlines()
    expected = {f"{tier} {case} passed" for tier, cases in (("T4", T4), ("T5", T5), ("T6", T6)) for case in cases}
    observed = [line for line in lines if line.startswith(("T4 ", "T5 ", "T6 ")) and line.endswith(" passed")]
    if len(observed) != len(expected) or set(observed) != expected:
        raise SystemExit("STOP: nested isolation log does not contain every successful case exactly once")


def make(work, commit, reference_path):
    media = work / "media"
    logs = work / "logs"
    required = {**BOOT_LOGS, "isolation.serial.log": "FIXTURE ISOLATION VERIFIED"}
    for log, marker in required.items():
        if marker.encode() not in (logs / log).read_bytes():
            raise SystemExit(f"STOP: missing successful evidence in {log}")
    isolation_evidence(logs / "isolation.serial.log")
    builder = {"account": pwd.getpwuid(os.getuid()).pw_name, "uid": os.getuid()}
    if builder["account"] != "otuken-ci-build" or work.stat().st_uid != builder["uid"]:
        raise SystemExit("STOP: provenance requires the dedicated build account")
    reviewed = reference(reference_path)
    agent_manifests = reference_path.parent / "agent-manifests"
    filesystem = matches_reference(work, reviewed, agent_manifests)
    images = check_inventoried_media(work)
    if sha(work / "fixture-recipe.sha256") != reviewed["recipe_sha256"]:
        raise SystemExit("STOP: fixture recipe differs from the reviewed reference")
    upstream = json.loads((work / "ubuntu/receipt.json").read_text())
    if upstream != reviewed["ubuntu"]:
        raise SystemExit("STOP: Ubuntu receipt differs from the reviewed reference")
    packages = {kind: package_manifest(work / f"{kind}-packages.sha256", kind, expected)
                for kind, expected in reviewed["package_manifest_sha256"].items()}
    evidence_dir = media / "evidence"
    evidence_dir.mkdir(mode=0o700, exist_ok=True)
    for name in (*required, "base.serial.log", "ext4-build.serial.log", "btrfs-build.serial.log"):
        shutil.copyfile(logs / name, evidence_dir / name)
    for name in ("fixture-recipe.sha256", "guest-packages.sha256", "tool-packages.sha256"):
        shutil.copyfile(work / name, evidence_dir / name)
    for origin, directory in (("agent", agent_manifests), ("cold", work / "manifests")):
        for role, path in manifest_paths(directory).items():
            shutil.copyfile(path, evidence_dir / f"{origin}.{role}.json.gz")
    record = {
        "schema": 4,
        "ubuntu": upstream,
        "images": images,
        "filesystem": filesystem,
        "build": {
            "commit": commit,
            "builder": builder,
            "reference_sha256": sha(reference_path),
            "recipe_sha256": sha(evidence_dir / "fixture-recipe.sha256"),
            "packages": packages,
        },
        "isolation": {
            "status": "passed",
            "log_sha256": sha(evidence_dir / "isolation.serial.log"),
            "boot_sha256": {name: sha(evidence_dir / name) for name in BOOT_LOGS},
        },
        "isolation_setup": "/opt/ci-fixture/isolation-setup",
    }
    temporary = media / ".provenance.tmp"
    temporary.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n")
    temporary.replace(media / "PROVENANCE.json")
    print(f"{sha(media / 'PROVENANCE.json')}  PROVENANCE.json")


if __name__ == "__main__":
    path, reviewed_commit, reviewed_reference = sys.argv[1:]
    make(Path(path), reviewed_commit, Path(reviewed_reference))
