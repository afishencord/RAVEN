import base64
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch

from tests.support import TEST_KEY, TEST_PASSWORD, encode_segment, independent_hs_token

import jwt
from pydantic import ValidationError

from app import auth
from app.config import Settings


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.claims = {"sub": "admin", "exp": int(time.time()) + 3600}

    def test_legacy_jose_compatible_hmac_tokens(self):
        for algorithm in ("HS256", "HS384", "HS512"):
            with self.subTest(algorithm=algorithm), patch.object(auth.settings, "jwt_algorithm", algorithm):
                token = independent_hs_token(self.claims, algorithm=algorithm)
                self.assertEqual(auth.decode_token(token), self.claims)

    def test_new_token_signature_and_claims_are_independently_compatible(self):
        before = int(time.time())
        token = auth.create_access_token("viewer")
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(base64.urlsafe_b64decode(header_part + "=="))
        payload = json.loads(base64.urlsafe_b64decode(payload_part + "=="))
        self.assertEqual(header, {"alg": "HS256", "typ": "JWT"})
        self.assertEqual(payload["sub"], "viewer")
        lifetime = auth.settings.access_token_expire_minutes * 60
        self.assertGreaterEqual(payload["exp"], before + lifetime)
        self.assertLessEqual(payload["exp"], int(time.time()) + lifetime)
        expected = hmac.new(TEST_KEY.encode(), f"{header_part}.{payload_part}".encode(), hashlib.sha256).digest()
        self.assertEqual(base64.urlsafe_b64decode(signature_part + "=="), expected)
        self.assertEqual(auth.decode_token(token), payload)

    def test_malformed_token_rejected(self):
        for token in ("", "not-a-token", "a.b.c", "...", "e30.e30.", "é.é.é"):
            with self.subTest(token=token):
                self.assertIsNone(auth.decode_token(token))

    def test_wrong_signing_key_rejected(self):
        self.assertIsNone(auth.decode_token(independent_hs_token(self.claims, key="other-public-test-key")))

    def test_tampered_subject_rejected(self):
        header, _, signature = independent_hs_token(self.claims).split(".")
        payload = encode_segment({**self.claims, "sub": "other-user"}).decode()
        self.assertIsNone(auth.decode_token(f"{header}.{payload}.{signature}"))

    def test_expired_and_current_second_expiration_rejected(self):
        for expiry in (0, int(time.time()) - 1, int(time.time())):
            with self.subTest(expiry=expiry):
                self.assertIsNone(auth.decode_token(independent_hs_token({**self.claims, "exp": expiry})))

    def test_missing_or_invalid_subject_rejected(self):
        claims = [{"exp": self.claims["exp"]}]
        claims.extend({**self.claims, "sub": value} for value in ("", None, 42, [], {}))
        for payload in claims:
            with self.subTest(claims=payload):
                self.assertIsNone(auth.decode_token(independent_hs_token(payload)))

    def test_missing_or_invalid_expiration_rejected(self):
        claims = [{"sub": "admin"}]
        claims.extend({**self.claims, "exp": value} for value in (None, "not-a-date", [], {}, float("inf")))
        for payload in claims:
            with self.subTest(claims=payload):
                self.assertIsNone(auth.decode_token(independent_hs_token(payload)))

    def test_invalid_not_before_and_issued_at_rejected(self):
        for claim in ("nbf", "iat"):
            for value in (int(time.time()) + 3600, "not-a-date", None, [], {}):
                with self.subTest(claim=claim, value=value):
                    self.assertIsNone(auth.decode_token(independent_hs_token({**self.claims, claim: value})))

    def test_unexpected_audience_rejected(self):
        self.assertIsNone(auth.decode_token(independent_hs_token({**self.claims, "aud": "other-app"})))

    def test_unsigned_token_rejected(self):
        self.assertIsNone(auth.decode_token(jwt.encode(self.claims, key="", algorithm="none")))

    def test_different_hmac_algorithm_rejected(self):
        for algorithm in ("HS384", "HS512"):
            with self.subTest(algorithm=algorithm):
                self.assertIsNone(auth.decode_token(independent_hs_token(self.claims, algorithm=algorithm)))

    def test_asymmetric_header_with_hmac_signature_rejected(self):
        for algorithm in ("RS256", "ES256", "EdDSA", "none"):
            with self.subTest(algorithm=algorithm):
                token = independent_hs_token(self.claims, header={"alg": algorithm, "typ": "JWT"})
                self.assertIsNone(auth.decode_token(token))

    def test_public_key_hmac_algorithm_confusion_rejected(self):
        # Even if an old asymmetric setting bypassed current Settings validation,
        # a token cannot change the server's allowed algorithm to HMAC. This is
        # public dummy key text, not an operational credential or RSA keypair.
        public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCyPublicTestFixture"
        token = independent_hs_token(self.claims, key=public_key)
        with patch.object(auth.settings, "jwt_algorithm", "RS256"), patch.object(auth.settings, "jwt_secret_key", public_key):
            self.assertIsNone(auth.decode_token(token))

    def test_key_from_untrusted_header_is_not_used(self):
        token = independent_hs_token(
            self.claims,
            key="attacker-controlled-public-test-key",
            header={"alg": "HS256", "typ": "JWT", "jwk": {"kty": "oct", "k": "YXR0YWNrZXI"}, "kid": "attacker"},
        )
        self.assertIsNone(auth.decode_token(token))


class ConfigurationAndPasswordTests(unittest.TestCase):
    def test_only_explicit_hmac_algorithm_configuration_is_accepted(self):
        for algorithm in ("HS256", "HS384", "HS512"):
            with self.subTest(algorithm=algorithm):
                self.assertEqual(Settings(_env_file=None, jwt_algorithm=algorithm).jwt_algorithm, algorithm)
        for algorithm in ("none", "None", "RS256", "ES256", "EdDSA", "HS256,RS256", "", "hs256"):
            with self.subTest(algorithm=algorithm), self.assertRaises(ValidationError):
                Settings(_env_file=None, jwt_algorithm=algorithm)

    def test_existing_bcrypt_password_workflow_is_unchanged(self):
        hashed = auth.get_password_hash(TEST_PASSWORD)
        self.assertTrue(hashed.startswith("$2b$"))
        self.assertTrue(auth.verify_password(TEST_PASSWORD, hashed))
        self.assertFalse(auth.verify_password("wrong-password", hashed))


if __name__ == "__main__":
    unittest.main()
