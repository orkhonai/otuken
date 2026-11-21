# SPDX-License-Identifier: MIT
"""Create only synthetic endpoints and controls for the disposable CI topology."""

import http.server
import json
import secrets
import signal
import socket
import socketserver
import sys
import threading
from pathlib import Path


def make(runtime):
    canary = secrets.token_hex(24)
    protected = {
        "ipv4-literal": "198.51.100.9", "ipv6-literal": "2001:db8:1234::9",
        "ipv4-private": "10.123.0.9", "ipv6-private": "fd5a:99::9",
        "ipv4-link-local": "169.254.50.9", "ipv6-link-local": "fe80::1234%fixture0",
        "ipv4-metadata": "169.254.169.254", "ipv6-metadata": "fd00:ec2::254",
        "ipv4-peer": "192.0.2.130", "ipv6-peer": "fd5a:2::20",
        "proxy-bypass": "192.0.2.129",
    }
    t5 = {name: {"kind": "tcp", "target": [address, 8080], "control": "worker-b"}
          for name, address in protected.items()}
    # Both families of the peer probe have live endpoints in worker B.
    t5["ipv6-peer"]["target"][1] = 8082
    t5.update({
        name: {"kind": "dns", "target": [domain, family], "control": "worker-b"}
        for name, domain, family in (
            ("dns-v4", "protected.fixture.test", "AF_INET"),
            ("dns-v6", "protected.fixture.test", "AF_INET6"),
            ("dns-unlisted-label", "unlisted.fixture.test", "AF_INET"),
        )
    })
    t5["redirect"] = {"kind": "http", "target": "http://192.0.2.1:8080/redirect", "control": "worker-b"}
    topology = {
        "guests": {f"worker-{role}": [f"fixture-{role}", f"worker-{role}"] for role in ("a", "b")},
        "canary": canary,
        "allow": [{"kind": "http", "target": url} for url in
                  ("http://192.0.2.1:8080/", "http://[fd5a:1::1]:8080/")],
        "t4": {
            "files": {"kind": "file", "target": "/var/lib/ci-fixture/secret"},
            "environment": {"kind": "env", "target": "FIXTURE_CANARY"},
            "network": {"kind": "http", "target": "http://192.0.2.130:8080/secret"},
            "guard-api": {"kind": "http", "target": "http://192.0.2.130:8081/secret"},
            "provider-cache": {"kind": "file", "target": "/var/cache/ci-fixture/provider"},
            "browser-profile": {"kind": "file", "target": "/var/lib/ci-fixture/browser/profile"},
            "volume": {"kind": "file", "target": "/mnt/fixture-volume/secret"},
        },
        "t5": t5,
        "t6": {
            "incus-admin": {"kind": "unix", "target": "/var/lib/incus/unix.socket", "control": "fixture-host"},
            "owner-socket": {"kind": "unix", "target": str(runtime / "owner.sock"), "control": "fixture-host"},
            "seat-channel": {"kind": "tcp", "target": ["192.0.2.129", 8099], "control": "worker-b"},
        },
    }
    (runtime / "canary").write_text(canary + "\n")
    (runtime / "topology.json").write_text(json.dumps(topology, indent=2) + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://198.51.100.9:8080/")
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"synthetic fixture endpoint\n")


class IPv6Server(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        super().server_bind()


class AcceptOnly(socketserver.BaseRequestHandler):
    def handle(self):
        return


def serve(runtime):
    servers = (
        http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Handler),
        IPv6Server(("::", 8080), Handler),
        http.server.ThreadingHTTPServer(("192.0.2.129", 8099), Handler),
        socketserver.UnixStreamServer(str(runtime / "owner.sock"), AcceptOnly),
    )
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    signal.pause()


if __name__ == "__main__":
    action, directory = sys.argv[1:]
    {"make": make, "serve": serve}[action](Path(directory))
