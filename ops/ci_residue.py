# SPDX-License-Identifier: MIT
"""Authorize only CI objects tied to the requested failed-run evidence."""

import json
import re
import sys
from pathlib import Path


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def owned_objects(instances, images, run, receipt):
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", run), "Invalid run name")
    hashes = set()
    for line in receipt.splitlines():
        match = re.fullmatch(r"otuken-ci-(ext4|btrfs) ([a-f0-9]{64})", line)
        require(match, "Unexpected image ownership record")
        hashes.add(match[2])
    objects = []
    for instance in instances:
        require(instance["name"] == "otuken-ci-test"
                and instance["config"].get("user.otuken-ci-run") == run,
                "Unrecognized instance in the CI project")
        objects.append(("vm", instance["name"]))
    for image in images:
        fingerprint = image["fingerprint"]
        require(fingerprint in hashes, "Unrecognized image in the CI project")
        objects.append(("image", fingerprint))
    return objects


if __name__ == "__main__":
    run, instances, images, evidence = sys.argv[1:]
    directory = Path(evidence)
    require(not (directory / "ci.ok").exists(), "The requested run is already marked successful")
    receipt = directory / "owned-images"
    for kind, name in owned_objects(json.loads(Path(instances).read_text()), json.loads(Path(images).read_text()),
                                    run, receipt.read_text() if receipt.exists() else ""):
        print(kind, name)
