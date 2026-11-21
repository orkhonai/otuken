# SPDX-License-Identifier: MIT
"""Assertions against the intentionally synthetic, offline isolation topology."""

import json
import subprocess
import sys
from pathlib import Path

PROBE = '''
import json
import os
import socket
import sys
import urllib.request
from pathlib import Path

kind, target = json.load(sys.stdin)
assert os.geteuid() == 0
socket.setdefaulttimeout(2)
try:
    if kind == "file":
        with Path(target).open("rb") as stream:
            result = stream.read(4096).decode(errors="replace")
    elif kind == "env":
        result = os.environ[target]
    elif kind == "dns":
        result = str(socket.getaddrinfo(target[0], None, getattr(socket, target[1])))
    elif kind == "http":
        assert target.startswith("http://")
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(target) as response:
            result = response.read(4096).decode(errors="replace")
    else:
        family = {"unix": socket.AF_UNIX, "vsock": socket.AF_VSOCK}.get(kind)
        if family is None:
            connection = socket.create_connection(tuple(target))
        else:
            connection = socket.socket(family, socket.SOCK_STREAM)
            connection.connect(target if kind == "unix" else tuple(target))
        connection.close()
        result = "connected"
    print(json.dumps({"allowed": True, "value": result}))
except (OSError, KeyError, ValueError):
    print(json.dumps({"allowed": False}))
'''

T4 = {"files", "environment", "network", "guard-api", "provider-cache",
      "browser-profile", "volume"}
T5 = {"ipv4-literal", "ipv6-literal", "ipv4-private", "ipv6-private", "ipv4-link-local",
      "ipv6-link-local", "ipv4-metadata", "ipv6-metadata", "ipv4-peer", "ipv6-peer",
      "dns-v4", "dns-v6", "dns-unlisted-label", "proxy-bypass", "redirect"}
T6 = {"incus-admin", "owner-socket", "seat-channel"}


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def probe(topology, client, check):
    command = ["python3", "-I", "-c", PROBE]
    if client != "fixture-host":
        project, instance = topology["guests"][client]
        command = ["incus", "--force-local", "--project", project, "exec", instance,
                   "--mode=non-interactive", "--", *command]
    result = subprocess.run(command, input=json.dumps([check["kind"], check["target"]]),
                            text=True, capture_output=True, check=True, timeout=12)
    return json.loads(result.stdout)


def verify(path):
    topology = json.loads(path.read_bytes())
    require(topology["guests"]["worker-a"] != topology["guests"]["worker-b"],
            "T4 needs separate worker VMs")
    canary = topology["canary"]
    require(isinstance(canary, str) and len(canary) >= 24, "Use a unique synthetic canary")
    allow = topology["allow"]
    require(probe(topology, "worker-a", allow[0])["allowed"] and probe(topology, "worker-a", allow[1])["allowed"],
            "T5 positive controls must reach the allowed service over both families")
    for label, required, checks in (("T4", T4, topology["t4"]), ("T5", T5, topology["t5"]),
                                    ("T6", T6, topology["t6"])):
        require(set(checks) == required, f"{label} fixture coverage differs")
        for name, check in sorted(checks.items()):
            control = probe(topology, "worker-b" if label == "T4" else check["control"], check)
            require(control["allowed"], f"{label} {name}: control failed to reach the fixture")
            observed = probe(topology, "worker-a", check)
            if label == "T4":
                require(canary in control.get("value", ""), f"T4 {name}: positive control lacks the canary")
                require(canary not in observed.get("value", ""), f"T4 {name}: canary leaked")
            else:
                require(not observed["allowed"], f"{label} {name}: prohibited access succeeded")
            print(f"{label} {name} passed")


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
