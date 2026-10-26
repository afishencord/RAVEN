"""Real stdlib socket/child-process tests; no Docker or application secrets."""
import argparse
import importlib.util
import json
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
for name in ("docker_smoke", "loopback_relay"):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    globals()[name] = module


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.sendall(self.request.recv(4096))


class RelayTests(unittest.TestCase):
    def test_private_target_validator_rejects_external_or_special_addresses(self):
        self.assertEqual(loopback_relay.private_ipv4("172.19.0.2"), "172.19.0.2")
        for value in ("8.8.8.8", "127.0.0.1", "0.0.0.0", "169.254.169.254", "224.0.0.1", "example.com", "::1"):
            with self.subTest(value=value), self.assertRaises((ValueError, argparse.ArgumentTypeError)):
                loopback_relay.private_ipv4(value)

    def test_actual_bidirectional_tcp_bytes_and_thread_cleanup(self):
        with socketserver.TCPServer(("127.0.0.1", 0), Echo) as target:
            target_thread = threading.Thread(target=target.serve_forever, daemon=True)
            target_thread.start()
            with loopback_relay.RelayServer(("127.0.0.1", 0), target.server_address) as relay:
                relay_thread = threading.Thread(target=relay.serve_forever, daemon=True)
                relay_thread.start()
                with socket.create_connection(relay.server_address, timeout=2) as client:
                    client.sendall(b"fixed-disposable-test-bytes")
                    self.assertEqual(client.recv(4096), b"fixed-disposable-test-bytes")
                relay.shutdown()
                relay_thread.join(timeout=2)
                self.assertFalse(relay_thread.is_alive())
            target.shutdown()
            target_thread.join(timeout=2)
            self.assertFalse(target_thread.is_alive())

    def snapshots(self, bindings=None):
        return {name: {"ports": {f"{port}/tcp": bindings}, "networks": {"project_default": {"IPAddress": "172.19.0.2"}}} for name, port in (("backend", 8000), ("frontend", 3000))}

    def test_only_absent_mappings_get_fixed_relay_destinations(self):
        targets = docker_smoke.relay_targets(self.snapshots())
        self.assertEqual(targets, {"backend": "172.19.0.2", "frontend": "172.19.0.2"})
        native = self.snapshots()
        for name, port in (("backend", 8000), ("frontend", 3000)):
            native[name]["ports"][f"{port}/tcp"] = [{"HostIp": "127.0.0.1", "HostPort": str(port)}]
        self.assertEqual(docker_smoke.relay_targets(native), {})
        for invalid in ([{"HostIp": "0.0.0.0", "HostPort": "8000"}], [{"HostIp": "127.0.0.1", "HostPort": "8001"}]):
            with self.assertRaises(docker_smoke.SmokeFailure):
                docker_smoke.relay_targets(self.snapshots(invalid))

    def test_effective_external_ip_cannot_become_relay_target(self):
        snapshots = self.snapshots()
        snapshots["backend"]["networks"]["project_default"]["IPAddress"] = "8.8.8.8"
        with self.assertRaises(docker_smoke.SmokeFailure):
            docker_smoke.relay_targets(snapshots)

    def test_real_child_lifecycle_closes_listener(self):
        # The production entry point has fixed listeners and destinations. No
        # remote connection is made unless a client sends data to a listener.
        with tempfile.TemporaryDirectory() as work:
            state = Path(work)
            proc = docker_smoke.start_relay(state, {"backend": "172.19.0.2"})
            try:
                deadline = time.monotonic() + 3
                while True:
                    self.assertIsNone(proc.poll())
                    with socket.socket() as probe:
                        try:
                            probe.bind(("127.0.0.1", 8000))
                        except OSError:
                            break  # The child has bound; do not probe any target.
                    if time.monotonic() >= deadline:
                        self.fail("Relay did not bind loopback")
                    time.sleep(0.01)
                docker_smoke.stop_relay(state)
                self.assertIsNotNone(proc.wait(timeout=3))
                self.assertFalse((state / "relay.json").exists())
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 8000))
            finally:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)

    def test_partial_listener_conflict_exits_and_closes_first_listener(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 3000))
            occupied.listen()
            result = subprocess.run([sys.executable, str(SCRIPTS / "loopback_relay.py"), "--backend-ip", "172.19.0.2", "--frontend-ip", "172.19.0.3"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
            self.assertNotEqual(result.returncode, 0)
            with socket.socket() as available:
                available.bind(("127.0.0.1", 8000))

    def test_cleanup_does_not_signal_reused_pid(self):
        with tempfile.TemporaryDirectory() as work:
            state = Path(work)
            command = [sys.executable, str(SCRIPTS / "loopback_relay.py"), "--backend-ip", "172.19.0.2"]
            (state / "relay.json").write_text(json.dumps({"pid": 12345, "start": "100", "command": command}))
            with patch.object(docker_smoke, "process_identity", return_value=("101", [b"unrelated"])), patch.object(docker_smoke.os, "kill") as kill:
                docker_smoke.stop_relay(state)
            kill.assert_not_called()

    def test_dead_relay_fails_readiness_before_any_http_request(self):
        with patch.object(docker_smoke.urllib.request, "build_opener") as opener:
            child = unittest.mock.Mock()
            child.poll.return_value = 1
            with self.assertRaises(docker_smoke.SmokeFailure):
                docker_smoke.wait_ready("http://127.0.0.1:8000/api/health", "loopback API", relay=child)
            opener.return_value.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
