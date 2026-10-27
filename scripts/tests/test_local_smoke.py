"""Stdlib-only host-harness isolation checks, not a deployment pass."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "local_smoke.py"
spec = importlib.util.spec_from_file_location("local_smoke", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class LocalHarnessTests(unittest.TestCase):
    def test_clean_environment_excludes_deployment_and_interpreter_configuration(self):
        inherited = {
            "PATH": "/bin:/usr/bin", "LANG": "C.UTF-8", "TERM": "xterm",
            "HOME": "/real/user", "DATABASE_URL": "sqlite:///real.db",
            "JWT_SECRET_KEY": "do-not-inherit", "FLOCK_INTERNAL_TOKEN": "do-not-inherit",
            "FLOCK_ENROLLMENT_TOKEN": "do-not-inherit", "OPENAI_API_KEY": "do-not-inherit",
            "BOOTSTRAP_ADMIN_PASSWORD": "do-not-inherit", "BOOTSTRAP_ADMIN_USERNAME": "real-user",
            "SSH_KNOWN_HOSTS_PATH": "/real/known_hosts", "HTTP_PROXY": "http://real-proxy",
            "PYTHONPATH": "/real/modules", "NODE_OPTIONS": "--require=/real/hook.js",
        }
        with patch.dict(os.environ, inherited, clear=True):
            self.assertEqual(smoke.clean_env(), {key: inherited[key] for key in ("PATH", "LANG", "TERM")})

    def test_assertion_failure_is_a_safe_harness_error(self):
        with self.assertRaisesRegex(smoke.SmokeFailure, "Static diagnostic"):
            smoke.check(False, "Static diagnostic")


if __name__ == "__main__":
    unittest.main()
