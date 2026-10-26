import time
import unittest
from unittest.mock import patch

from tests.support import TEST_PASSWORD, independent_hs_token

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import auth, database, main, main_flock
from app.database import Base
from app.deps import get_db
from app.models import User


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = auth.get_password_hash(TEST_PASSWORD)

    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            db.add_all(
                User(username=role, full_name=f"Test {role}", role=role, hashed_password=self.password_hash)
                for role in ("viewer", "operator", "admin")
            )
            db.add(User(username="inactive", full_name="Inactive", role="admin", is_active=False, hashed_password=self.password_hash))
            db.commit()

        def test_db():
            with self.sessions() as db:
                yield db

        main.app.dependency_overrides[get_db] = test_db
        # Deliberately no lifespan here: no seed data, monitoring, networking,
        # runner or real database. Lifespan is exercised separately below.
        self.client = TestClient(main.app)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(main.app.dependency_overrides.clear)
        self.addCleanup(self.client.close)

    def headers(self, username):
        return {"Authorization": f"Bearer {auth.create_access_token(username)}"}

    def test_json_login_and_me_for_every_role(self):
        for role in ("viewer", "operator", "admin"):
            with self.subTest(role=role):
                response = self.client.post("/api/auth/login", json={"username": role, "password": TEST_PASSWORD})
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["token_type"], "bearer")
                self.assertEqual(body["user"]["role"], role)
                self.assertNotIn("hashed_password", body["user"])
                me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
                self.assertEqual(me.status_code, 200, me.text)
                self.assertEqual(me.json(), body["user"])

    def test_invalid_or_inactive_login_returns_generic_401(self):
        for username, password in (("admin", "wrong"), ("missing", TEST_PASSWORD), ("inactive", TEST_PASSWORD)):
            with self.subTest(username=username):
                response = self.client.post("/api/auth/login", json={"username": username, "password": password})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json(), {"detail": "Invalid username or password"})

    def test_json_login_input_validation(self):
        for payload in ({}, {"username": "admin"}, {"username": [], "password": TEST_PASSWORD}, None):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/auth/login", json=payload).status_code, 422)

    def test_login_does_not_accept_form_instead_of_json(self):
        response = self.client.post("/api/auth/login", data={"username": "admin", "password": TEST_PASSWORD})
        self.assertEqual(response.status_code, 422)

    def test_legacy_compatible_token_can_access_me(self):
        token = independent_hs_token({"sub": "viewer", "exp": int(time.time()) + 3600})
        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "viewer")

    def test_unauthenticated_and_invalid_tokens_return_401(self):
        expired = independent_hs_token({"sub": "admin", "exp": 0})
        missing_exp = independent_hs_token({"sub": "admin"})
        wrong_alg = independent_hs_token({"sub": "admin", "exp": int(time.time()) + 3600}, algorithm="HS512")
        for value in (None, "Basic admin", "Bearer", "Bearer malformed", f"Bearer {expired}", f"Bearer {missing_exp}", f"Bearer {wrong_alg}"):
            with self.subTest(authorization=value):
                response = self.client.get("/api/auth/me", headers={"Authorization": value} if value else {})
                self.assertEqual(response.status_code, 401, response.text)

    def test_inactive_or_deleted_users_cannot_use_previously_issued_token(self):
        for username in ("inactive", "does-not-exist"):
            with self.subTest(username=username):
                self.assertEqual(self.client.get("/api/auth/me", headers=self.headers(username)).status_code, 401)
        headers = self.headers("admin")
        with self.sessions() as db:
            db.query(User).filter_by(username="admin").update({"is_active": False})
            db.commit()
        self.assertEqual(self.client.get("/api/auth/me", headers=headers).status_code, 401)

    def test_database_role_not_token_claim_controls_admin_access(self):
        claims = {"sub": "viewer", "role": "admin", "exp": int(time.time()) + 3600}
        response = self.client.get("/api/credentials", headers={"Authorization": f"Bearer {independent_hs_token(claims)}"})
        self.assertEqual(response.status_code, 403)
        admin_headers = self.headers("admin")
        self.assertEqual(self.client.get("/api/credentials", headers=admin_headers).status_code, 200)
        with self.sessions() as db:
            db.query(User).filter_by(username="admin").update({"role": "viewer"})
            db.commit()
        self.assertEqual(self.client.get("/api/credentials", headers=admin_headers).status_code, 403)

    def test_read_and_admin_role_routes(self):
        for role in ("viewer", "operator", "admin"):
            with self.subTest(role=role):
                headers = self.headers(role)
                self.assertEqual(self.client.get("/api/nodes", headers=headers).status_code, 200)
                self.assertEqual(self.client.get("/api/credentials", headers=headers).status_code, 200 if role == "admin" else 403)
                response = self.client.post("/api/node-groups", headers=headers, json={"name": f"Test {role}"})
                self.assertEqual(response.status_code, 201 if role == "admin" else 403, response.text)

    def test_operator_routes_enforce_role_before_lookup(self):
        # A nonexistent incident avoids any remediation or side effects: allowed
        # roles reach the 404 lookup; viewers are denied before it.
        for role in ("viewer", "operator", "admin"):
            with self.subTest(role=role):
                response = self.client.post("/api/incidents/99999/acknowledge", headers=self.headers(role))
                self.assertEqual(response.status_code, 403 if role == "viewer" else 404, response.text)

    def test_health_openapi_and_cors(self):
        self.assertEqual(self.client.get("/").json()["status"], "ok")
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/health").json(), {"status": "healthy"})
        schema = self.client.get("/openapi.json")
        self.assertEqual(schema.status_code, 200)
        self.assertIn("/api/auth/login", schema.json()["paths"])
        headers = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"}
        response = self.client.options("/api/auth/login", headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:3000")
        headers["Origin"] = "https://untrusted.example"
        self.assertEqual(self.client.options("/api/auth/login", headers=headers).status_code, 400)

    def test_backend_and_flock_lifespans_on_isolated_database(self):
        for module in (main, main_flock):
            with self.subTest(module=module.__name__), patch.object(module, "engine", self.engine), patch.object(module, "SessionLocal", self.sessions), patch.object(database, "engine", self.engine):
                with TestClient(module.app) as client:
                    self.assertEqual(client.get("/api/health").status_code, 200)
                    self.assertEqual(client.get("/openapi.json").status_code, 200)
                self.assertIsNone(main.monitoring_service._task)


if __name__ == "__main__":
    unittest.main()
