# SPDX-License-Identifier: MIT

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def load(path):
    value = json.loads(Path(path).read_bytes())
    return value.get("metadata", value)


def check(condition, message):
    if not condition:
        sys.exit(f"CI preflight: {message}")


project, profile, pool, pool_path = sys.argv[1:]
configured = load(project)["config"]
required = {
    "restricted": "true", "features.images": "true", "features.profiles": "true",
    "features.networks": "true", "limits.networks": "0", "limits.containers": "0",
    "limits.virtual-machines": "1", "limits.instances": "1", "limits.cpu": "4",
    "limits.memory": "8GiB", "limits.disk": "80GiB",
    "restricted.devices.disk": "managed", "restricted.devices.nic": "block",
    "restricted.storage-pools.access": "otuken-ci",
    "restricted.virtual-machines.lowlevel": "block",
}
check(all(configured.get(key) == value for key, value in required.items()), "project limits differ")
configured_profile = load(profile)
check(configured_profile["config"] == {"limits.cpu": "4", "limits.memory": "8GiB",
                                       "boot.autostart": "false"}, "unexpected VM profile settings")
check(configured_profile["devices"] == {"root": {
    "path": "/", "pool": "otuken-ci", "size": "32GiB", "type": "disk",
    "limits.max": "25MiB,400iops",
}}, "profile differs from the NIC-free, I/O-capped profile")
usage = shutil.disk_usage(pool_path)
check(usage.free - 80 * 1024**3 >= usage.total * 35 // 100, "80 GiB reservation would cross the 35% floor")

configured_pool = load(pool)
check(configured_pool["driver"] == "dir" and configured_pool["config"].get("volume.size") == "32GiB",
      "unexpected pool driver or default VM disk size")
meminfo = Path("/proc/meminfo").read_text().splitlines()
available = next(int(line.split()[1]) for line in meminfo if line.startswith("MemAvailable:"))
check(available >= 24 * 1024**2, "less than 24 GiB RAM available")

device = subprocess.check_output(["/usr/bin/findmnt", "-n", "-o", "SOURCE", "-T", pool_path],
                                 text=True).strip().split("[", 1)[0]
mapped = Path(device).stat().st_rdev
block = f"{os.major(mapped)}:{os.minor(mapped)}"
group = Path("/sys/fs/cgroup/system.slice/incus.service")
quota, period = map(int, (group / "cpu.max").read_text().split())
check(quota == 4 * period, "Incus service CPU quota differs")
io = {row[0]: row[1:] for line in (group / "io.max").read_text().splitlines() if (row := line.split())}
check({"rbps=40000000", "wbps=25000000"} <= set(io.get(block, [])), "Incus daemon lacks the root block I/O cap")
