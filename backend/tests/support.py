"""Public test fixtures only; never read deployment secrets or use its database."""

import base64
import hashlib
import hmac
import json
import os

TEST_KEY = "public-test-fixture-not-a-deployment-secret-0123456789-abcdefghijklmnop"
TEST_PASSWORD = "public-test-password"

# Read config definitions only (no settings instantiated), disable dotenv, and
# clear every app-owned field so tests never consume a real deployment's config.
from app.config import AgentSettings, EnvironmentSettings, Settings

for settings_type in (EnvironmentSettings, AgentSettings, Settings):
    settings_type.model_config["env_file"] = None
for key in list(os.environ):
    if key.casefold() in Settings.model_fields:
        os.environ.pop(key, None)

# Set before importing app modules, which cache settings at import time.
os.environ.update(
    DATABASE_URL="sqlite://",
    JWT_SECRET_KEY=TEST_KEY,
    JWT_ALGORITHM="HS256",
    OPENAI_API_KEY="",
    EMBEDDED_MONITORING="false",
    FLOCK_INTERNAL_TOKEN="public-test-internal-token-not-a-deployment-secret",
    FLOCK_ENROLLMENT_TOKEN="public-test-enrollment-token-not-a-deployment-secret",
    SSH_KNOWN_HOSTS_PATH="",
    FRONTEND_ORIGIN="http://localhost:3000",
)


def encode_segment(value):
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")


def independent_hs_token(claims, key=TEST_KEY, algorithm="HS256", header=None):
    """JOSE compact/HMAC wire format, independent of the library under test.

    python-jose's existing HS256 tokens use the same header, compact JSON,
    NumericDate expiration and unpadded base64url encoding. Keeping this helper
    dependency-free avoids retaining python-jose/ecdsa just for migration tests.
    """
    header = header or {"alg": algorithm, "typ": "JWT"}
    signing_input = encode_segment(header) + b"." + encode_segment(claims)
    digest = {"HS256": hashlib.sha256, "HS384": hashlib.sha384, "HS512": hashlib.sha512}[algorithm]
    signature = base64.urlsafe_b64encode(hmac.new(key.encode(), signing_input, digest).digest()).rstrip(b"=")
    return (signing_input + b"." + signature).decode()
