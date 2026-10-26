import contextlib
import importlib.util
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("bootstrap_env", Path(__file__).resolve().parents[1] / "bootstrap_env.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class PrivateEnvTests(unittest.TestCase):
    def test_private_unique_secret_generation_and_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            output = io.StringIO()
            with patch("sys.argv", ["bootstrap_env.py", "--output", str(path)]), contextlib.redirect_stdout(output):
                self.assertEqual(bootstrap.main(), 0)
            values = dict(line.split("=", 1) for line in path.read_text().splitlines() if line and not line.startswith("#"))
            secrets = [values[key] for key in ("JWT_SECRET_KEY", "FLOCK_INTERNAL_TOKEN", "FLOCK_ENROLLMENT_TOKEN")]
            self.assertEqual(len(set(secrets)), 3)
            self.assertTrue(all(len(value) == 64 for value in secrets))
            self.assertTrue(all(value not in output.getvalue() for value in secrets))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(values["EMBEDDED_MONITORING"], "false")
            self.assertFalse(any("PASSWORD" in key for key in values))
            other = Path(directory) / ".env.other"
            bootstrap.create_env(other)
            self.assertNotEqual(path.read_text(), other.read_text())

    def test_never_overwrites_existing_file_or_follows_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("keep this existing configuration")
            with self.assertRaises(FileExistsError):
                bootstrap.create_env(path)
            link = Path(directory) / ".env.link"
            link.symlink_to(path)
            with self.assertRaises(FileExistsError):
                bootstrap.create_env(link)
            self.assertEqual(path.read_text(), "keep this existing configuration")

    def test_rejects_nonignored_destinations_and_tracked_example(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("settings.txt", ".env.example"):
                path = Path(directory) / name
                with self.assertRaises(ValueError):
                    bootstrap.create_env(path)
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
