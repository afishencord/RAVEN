"""Stdlib-only safety tests; these are not a Docker build or deployment pass."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "docker_smoke.py"
spec = importlib.util.spec_from_file_location("docker_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "private"

    def model(self):
        env = {"EMBEDDED_MONITORING": "false", "OPENAI_API_KEY": "", "DATABASE_URL": "sqlite:////data/raven.db", "JWT_SECRET_KEY": "a" * 64, "FLOCK_INTERNAL_TOKEN": "b" * 64, "FLOCK_ENROLLMENT_TOKEN": "c" * 64}
        services = {}
        for name in smoke.SERVICES:
            services[name] = {"restart": "no", "logging": {"driver": "none"}, "networks": {"default": {}}, "environment": env.copy(), "build": {"context": str(smoke.ROOT / ("frontend" if name == "frontend" else "backend"))}}
        for name, port in (("backend", 8000), ("frontend", 3000)):
            services[name]["ports"] = [{"target": port, "published": str(port), "host_ip": "127.0.0.1"}]
        services["frontend"]["build"]["args"] = {"NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8000/api"}
        return {"services": services, "networks": {"default": {"internal": True}}}

    def test_safe_effective_model_is_accepted(self):
        smoke.validate_config(self.model(), self.state)

    def test_effective_model_rejects_public_extra_or_hidden_ports(self):
        for service, change in (("backend", {"host_ip": "0.0.0.0"}), ("frontend", {"published": "3001"})):
            with self.subTest(service=service):
                model = self.model()
                model["services"][service]["ports"][0].update(change)
                with self.assertRaises(smoke.SmokeFailure):
                    smoke.validate_config(model, self.state)
        model = self.model()
        model["services"]["flock"]["ports"] = [{"target": 8000, "published": "8001", "host_ip": "127.0.0.1"}]
        with self.assertRaises(smoke.SmokeFailure):
            smoke.validate_config(model, self.state)

    def test_effective_model_rejects_unsafe_runtime_settings(self):
        for key, value in (("OPENAI_API_KEY", "not-a-real-key"), ("EMBEDDED_MONITORING", "true"), ("DATABASE_URL", "sqlite:///production.db"), ("FLOCK_INTERNAL_TOKEN", "dev-flock-internal-token")):
            with self.subTest(key=key):
                model = self.model()
                model["services"]["backend"]["environment"][key] = value
                with self.assertRaises(smoke.SmokeFailure):
                    smoke.validate_config(model, self.state)
        model = self.model()
        model["networks"]["default"]["internal"] = False
        with self.assertRaises(smoke.SmokeFailure):
            smoke.validate_config(model, self.state)

    def test_effective_model_rejects_unsafe_mount(self):
        for mount in ({"type": "bind", "source": "/var/run/docker.sock", "read_only": True}, {"type": "bind", "source": str(self.state / "passwords.json"), "read_only": False}):
            model = self.model()
            model["services"]["backend"]["volumes"] = [mount]
            with self.assertRaises(smoke.SmokeFailure):
                smoke.validate_config(model, self.state)

    def test_prepare_generates_unique_secrets_in_private_directory(self):
        old_umask = os.umask(0o077)
        try:
            smoke.prepare(self.state)
        finally:
            os.umask(old_umask)
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.state / "test.env").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.state / "passwords.json").stat().st_mode), 0o444)
        passwords = json.loads((self.state / "passwords.json").read_text())
        self.assertEqual(set(passwords), {"admin", "operator", "viewer"})
        self.assertEqual(len(set(passwords.values())), 3)
        self.assertTrue(all(len(value) >= 40 for value in passwords.values()))
        text = (self.state / "test.env").read_text()
        self.assertNotIn("dev-", text)
        with self.assertRaises(FileExistsError):
            smoke.prepare(self.state)

    def test_partial_preparation_removes_private_files(self):
        with patch.object(smoke, "render_override", side_effect=OSError("test interruption")):
            with self.assertRaises(OSError):
                smoke.prepare(self.state)
        self.assertFalse(self.state.exists())

    def test_build_diagnostic_tail_redacts_generated_values(self):
        with patch.object(smoke.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "::error::private-test-secret")), patch("builtins.print") as output:
            with self.assertRaises(smoke.SmokeFailure):
                smoke.execute(["docker"], "image build", build_redactions=["private-test-secret"])
        self.assertEqual(output.call_args.args[0], "build | ::error::[REDACTED]")

    def test_override_replaces_dangerous_base_fields_without_duplicate_keys(self):
        value = smoke.render_override(self.state, "raven-smoke-" + "a" * 16)
        self.assertEqual(value.count("container_name: !reset null"), 5)
        self.assertEqual(value.count("env_file: !override"), 5)
        self.assertEqual(value.count("ports: !override"), 5)
        self.assertEqual(value.count("environment: !override"), 5)
        self.assertNotIn("dev-flock-", value)
        # Every four-space service field must be unique within its section.
        fields = set()
        for line in value.splitlines():
            if line.startswith("  ") and not line.startswith("    "):
                fields = set()
            elif line.startswith("    ") and not line.startswith("      "):
                key = line.strip().split(":", 1)[0]
                self.assertNotIn(key, fields)
                fields.add(key)

    def test_clean_env_does_not_forward_app_secrets_or_docker_context(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret", "COMPOSE_FILE": "unsafe.yml", "DOCKER_HOST": "ssh://production", "HTTP_PROXY": "http://proxy"}):
            env = smoke.clean_env()
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertNotIn("COMPOSE_FILE", env)
        self.assertNotIn("DOCKER_HOST", env)
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(smoke.DOCKER[-1], "unix:///var/run/docker.sock")

    def test_cleanup_refuses_unmarked_directory(self):
        self.state.mkdir()
        with self.assertRaises(smoke.SmokeFailure):
            smoke.cleanup(self.state)
        self.assertTrue(self.state.exists())

    def test_cleanup_removes_only_confirmed_project_and_verifies_resources(self):
        smoke.prepare(self.state)
        with patch.object(smoke, "execute", return_value=subprocess.CompletedProcess([], 0, "")) as execute:
            smoke.cleanup(self.state)
        self.assertFalse(self.state.exists())
        self.assertEqual(execute.call_count, 4)
        self.assertIn("--volumes", execute.call_args_list[0].args[0])
        for call in execute.call_args_list[1:]:
            self.assertIn("--filter", call.args[0])
            self.assertTrue(call.args[0][-1].startswith("label=com.docker.compose.project=raven-smoke-"))

    def test_cleanup_keeps_state_when_docker_down_fails(self):
        smoke.prepare(self.state)
        with patch.object(smoke, "execute", return_value=subprocess.CompletedProcess([], 1, "private error")):
            with self.assertRaises(smoke.SmokeFailure):
                smoke.cleanup(self.state)
        self.assertTrue((self.state / "test.env").exists())

    def test_command_errors_never_expose_captured_output(self):
        with patch.object(smoke.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "a-private-secret")):
            with self.assertRaises(smoke.SmokeFailure) as failure:
                smoke.execute(["docker"], "safe phase")
        self.assertNotIn("a-private-secret", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
