import os
import unittest
from unittest.mock import patch

from tests.support import TEST_KEY, TEST_PASSWORD

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import bootstrap, seed
from app.auth import get_password_hash, verify_password
from app.config import AgentSettings, Settings
from app.database import Base
from app.models import Credential, FlockEnrollmentToken, FlockPolicy, User


class ConfigurationTests(unittest.TestCase):
    def settings(self, **kwargs):
        return Settings(_env_file=None, jwt_secret_key=TEST_KEY, flock_internal_token="public-test-internal-token-only-0123456789", **kwargs)

    def test_missing_secrets_fail_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            for kwargs in ({}, {"jwt_secret_key": TEST_KEY}, {"flock_internal_token": TEST_KEY}):
                with self.subTest(keys=list(kwargs)), self.assertRaises(ValidationError):
                    Settings(_env_file=None, **kwargs)

    def test_empty_short_placeholder_and_control_secrets_fail_without_echo(self):
        values = ("", "short", "change-me-in-env", "replace-this-with-a-long-random-secret", "dev-flock-internal-token", "your-" + "x" * 40, "x" * 40 + "\x00", "x" * 40 + "\n")
        with patch.dict(os.environ, {}, clear=True):
            for field in ("jwt_secret_key", "flock_internal_token", "flock_enrollment_token"):
                for value in values:
                    if field == "flock_enrollment_token" and not value:
                        continue  # No configured enrollment token is valid.
                    with self.subTest(field=field, value_length=len(value)):
                        inputs = dict(jwt_secret_key=TEST_KEY, flock_internal_token=TEST_KEY, flock_enrollment_token=None)
                        inputs[field] = value
                        with self.assertRaises(ValidationError) as error:
                            Settings(_env_file=None, **inputs)
                        if value:
                            self.assertNotIn(repr(value), str(error.exception))

    def test_enrollment_bcrypt_byte_limit_and_no_privileged_agent_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(AgentSettings(_env_file=None).flock_enrollment_token)
            agent = AgentSettings(_env_file=None, flock_enrollment_token="a" * 72)
            self.assertFalse(hasattr(agent, "jwt_secret_key"))
            self.assertFalse(hasattr(agent, "flock_internal_token"))
            for token in ("a" * 73, "é" * 37):
                with self.assertRaises(ValidationError):
                    AgentSettings(_env_file=None, flock_enrollment_token=token)

    def test_secrets_not_in_settings_repr(self):
        settings = self.settings(bootstrap_admin_password=TEST_PASSWORD)
        for value in (settings.jwt_secret_key, settings.flock_internal_token, TEST_PASSWORD):
            self.assertNotIn(value, repr(settings))

    def test_admin_password_validation_prevents_short_or_truncated_passwords(self):
        for password in ("", "admin123!", "x" * 73, "é" * 37, "x" * 16 + "\x00"):
            with self.subTest(password_length=len(password)), self.assertRaises(ValidationError):
                self.settings(bootstrap_admin_password=password)


class BootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safe_hash = get_password_hash(TEST_PASSWORD)
        cls.demo_hashes = [get_password_hash(password) for password in bootstrap.LEGACY_DEMO_PASSWORDS]
        cls.demo_token_hash = get_password_hash(bootstrap.LEGACY_ENROLLMENT_TOKEN)

    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine, expire_on_commit=False)()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        self.settings = Settings(_env_file=None, bootstrap_admin_username=None, bootstrap_admin_password=None, flock_enrollment_token=None)
        self.patcher = patch.object(seed, "get_settings", return_value=self.settings)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def add_user(self, name="chosen-admin", password_hash=None, role="admin", active=True):
        user = User(username=name, full_name="Test", hashed_password=password_hash or self.safe_hash, role=role, is_active=active)
        self.db.add(user)
        self.db.commit()
        return user

    def add_token(self, hashed=None, enabled=True):
        token = FlockEnrollmentToken(name="local-linux-unix-enrollment", token_hash=hashed or self.demo_token_hash, is_enabled=enabled)
        self.db.add(token)
        self.db.commit()
        return token

    def test_empty_database_without_admin_config_refuses_and_creates_nothing(self):
        with self.assertRaisesRegex(RuntimeError, "init-admin"):
            seed.seed_data(self.db)
        self.assertEqual(self.db.query(User).count(), 0)
        self.assertEqual(self.db.query(Credential).count(), 0)
        self.assertEqual(self.db.query(FlockPolicy).count(), 0)

    def test_explicit_empty_database_admin_only_and_optional_enrollment(self):
        self.settings.bootstrap_admin_username = "my-first-admin"
        self.settings.bootstrap_admin_password = TEST_PASSWORD
        seed.seed_data(self.db)
        user = self.db.query(User).one()
        self.assertEqual((user.username, user.role), ("my-first-admin", "admin"))
        self.assertTrue(verify_password(TEST_PASSWORD, user.hashed_password))
        self.assertEqual(self.db.query(Credential).count(), 0)
        self.assertEqual(self.db.query(FlockEnrollmentToken).count(), 0)
        self.assertEqual(self.db.query(FlockPolicy).one().command_allowlist, [])

    def test_existing_users_preserved_ignoring_bootstrap_config(self):
        user = self.add_user()
        self.settings.bootstrap_admin_username = "must-not-create"
        self.settings.bootstrap_admin_password = "different-public-fixture-password"
        seed.seed_data(self.db)
        self.assertEqual(self.db.query(User).count(), 1)
        self.assertEqual(user.hashed_password, self.safe_hash)
        self.assertTrue(user.is_active)

    def test_initial_admin_command_refuses_existing_users(self):
        bootstrap.create_initial_admin(self.db, "selected-user", TEST_PASSWORD)
        with self.assertRaisesRegex(ValueError, "already exist"):
            bootstrap.create_initial_admin(self.db, "other-user", TEST_PASSWORD)
        self.assertEqual(self.db.query(User).count(), 1)

    def test_known_demo_accounts_detected_even_if_renamed_and_not_mutated(self):
        for index, hashed in enumerate(self.demo_hashes):
            self.add_user(f"renamed-{index}", hashed, role="viewer")
        with self.assertRaisesRegex(RuntimeError, "legacy demo access"):
            seed.seed_data(self.db)
        self.assertEqual(self.db.query(User).filter_by(is_active=True).count(), 3)

    def test_known_demo_enrollment_refuses_startup_without_mutation(self):
        self.add_user()
        token = self.add_token()
        with self.assertRaisesRegex(RuntimeError, "legacy demo access"):
            seed.seed_data(self.db)
        self.assertTrue(token.is_enabled)
        self.assertEqual(token.token_hash, self.demo_token_hash)

    def test_disable_requires_remaining_safe_admin_and_preserves_records(self):
        user = self.add_user(password_hash=self.demo_hashes[0])
        token = self.add_token()
        with self.assertRaisesRegex(ValueError, "active administrator"):
            bootstrap.disable_demo_access(self.db)
        self.assertTrue(user.is_active)
        self.assertTrue(token.is_enabled)
        bootstrap.reset_password(self.db, user.username, TEST_PASSWORD)
        viewer = self.add_user("legacy-viewer", self.demo_hashes[2], role="viewer")
        self.assertEqual(bootstrap.disable_demo_access(self.db), (1, 1))
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, "admin")
        self.assertFalse(viewer.is_active)
        self.assertFalse(token.is_enabled)
        self.assertEqual(self.db.query(User).count(), 2)
        self.assertEqual(self.db.query(FlockEnrollmentToken).count(), 1)
        seed.seed_data(self.db)  # Disabled legacy rows are safe and stay disabled.
        self.assertFalse(viewer.is_active)
        self.assertFalse(token.is_enabled)

    def test_reset_preserves_role_and_disabled_state_and_never_creates_user(self):
        user = self.add_user(role="viewer", active=False)
        bootstrap.reset_password(self.db, user.username, "new-public-test-password")
        self.assertEqual(user.role, "viewer")
        self.assertFalse(user.is_active)
        with self.assertRaisesRegex(ValueError, "No such user"):
            bootstrap.reset_password(self.db, "missing", TEST_PASSWORD)

    def test_env_never_reenables_or_rotates_existing_enrollment(self):
        self.add_user()
        token = self.add_token(enabled=False)
        self.settings.flock_enrollment_token = "new-public-enrollment-fixture-0123456789"
        seed.seed_data(self.db)
        self.assertFalse(token.is_enabled)
        self.assertEqual(token.token_hash, self.demo_token_hash)
        bootstrap.rotate_enrollment(self.db, self.settings.flock_enrollment_token)
        self.assertTrue(token.is_enabled)
        self.assertTrue(verify_password(self.settings.flock_enrollment_token, token.token_hash))
        self.assertFalse(verify_password(bootstrap.LEGACY_ENROLLMENT_TOKEN, token.token_hash))
        seed.seed_data(self.db)

    def test_explicit_enrollment_rotator_refuses_missing_or_legacy_secret(self):
        token = self.add_token(enabled=False)
        for secret in (None, "", bootstrap.LEGACY_ENROLLMENT_TOKEN):
            with self.assertRaises(ValueError):
                bootstrap.rotate_enrollment(self.db, secret)
        self.assertFalse(token.is_enabled)

    def test_existing_default_policy_preserved(self):
        self.add_user()
        policy = FlockPolicy(name="Managed policy", description="Test", is_default=True, command_allowlist=["uname -s"])
        self.db.add(policy)
        self.db.commit()
        seed.seed_data(self.db)
        self.assertTrue(policy.is_default)
        self.assertEqual(policy.command_allowlist, ["uname -s"])
        self.assertEqual(self.db.query(FlockPolicy).filter_by(is_default=True).count(), 1)

    def test_password_input_refuses_nonterminal(self):
        with patch.object(bootstrap.sys.stdin, "isatty", return_value=False), patch.object(bootstrap.getpass, "getpass") as prompt:
            with self.assertRaisesRegex(ValueError, "interactive terminal"):
                bootstrap._read_password()
            prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
