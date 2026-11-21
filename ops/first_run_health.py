# SPDX-License-Identifier: MIT
"""Snapshot read-only host availability checks without printing live addressing."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HEALTH_URL_ENV = "OTUKEN_CI_HEALTH_URL"


def read(*args):
    return subprocess.check_output(args, text=True, timeout=30)


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def validate_url(url):
    if url is None or url == "":
        return None
    require(bool(re.fullmatch(r"https?://[^\s]+", url)), "Invalid optional HTTP health probe URL")
    return url


def firewall_shape(raw):
    shaped = []
    for row in json.loads(raw)["nftables"]:
        for kind, data in row.items():
            if kind in {"metainfo", "element"}:
                continue
            clean = {name: value for name, value in data.items() if name != "handle"}
            if kind in {"set", "map"}:
                clean.pop("elem", None)
            shaped.append({kind: clean})
    return shaped


def probe_http(url):
    code = read("/usr/bin/curl", "--noproxy", "*", "--max-time", "10", "--silent", "--show-error",
                "--output", "/dev/null", "--write-out", "%{http_code}", "--", url)
    return {"url": url, "status": code}


def snapshot(health_url=None):
    url = validate_url(health_url)
    ssh = subprocess.run(["/usr/bin/systemctl", "is-active", "--quiet", "ssh.service", "ssh.socket"],
                         check=False, timeout=8).returncode == 0
    dns = read("/usr/bin/resolvectl", "query", "ubuntu.com")
    http_probe = probe_http(url) if url else None
    listeners = sorted({(row[0], row[4]) for line in read("/usr/bin/ss", "-H", "-lntu").splitlines()
                        if (row := line.split()) and len(row) >= 5})
    rules = firewall_shape(read("/usr/sbin/nft", "-j", "-s", "list", "ruleset"))
    return {"ssh": ssh, "dns": bool(dns.strip()), "http_probe": http_probe, "firewall": rules,
            "listeners": listeners, "resolver_link": str(Path("/etc/resolv.conf").readlink())}


def compare(baseline, now):
    require(now["ssh"] and now["dns"], "STOP: local SSH service or resolved check failed")
    require(now.get("http_probe") == baseline.get("http_probe"),
            "STOP: optional HTTP health probe status changed")
    require(now["resolver_link"] == baseline["resolver_link"], "STOP: resolver link changed")
    require(now["firewall"] == baseline["firewall"], "STOP: firewall policy shape changed")
    return now["listeners"] != baseline["listeners"]


def main():
    root, stage = sys.argv[1:]
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", stage), "Invalid health check stage")
    health = Path(root) / "health"
    health.mkdir(mode=0o700, exist_ok=True)
    baseline_path = health / "baseline.json"
    if stage == "baseline" and not baseline_path.exists():
        url = validate_url(os.environ.get(HEALTH_URL_ENV))
        now = snapshot(url)
        now["listeners"] = [list(row) for row in now["listeners"]]
        http_ok = True
        if now["http_probe"] is not None:
            status = now["http_probe"]["status"]
            http_ok = status.isdigit() and (200 <= int(status) < 400 or status in {"401", "403"})
        require(now["ssh"] and now["dns"] and http_ok,
                "STOP: establish healthy SSH, DNS, and any configured HTTP probe before changing the host")
        with baseline_path.open("x") as record:
            json.dump(now, record, indent=2)
        print("Baseline local checks OK")
        return
    require(baseline_path.is_file(), "STOP: capture the baseline before the maintenance run")
    baseline = json.loads(baseline_path.read_text())
    url = (baseline.get("http_probe") or {}).get("url")
    now = snapshot(url)
    now["listeners"] = [list(row) for row in now["listeners"]]
    (health / f"{stage}-latest.json").write_text(json.dumps(now, indent=2) + "\n")
    delta = compare(baseline, now)
    if delta:
        print("REVIEW: TCP/UDP listener addresses changed; compare private evidence before continuing")
    print(f"Local checks OK: {stage}; verify your independent SSH access path")


if __name__ == "__main__":
    main()
