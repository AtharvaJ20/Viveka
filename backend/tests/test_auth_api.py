"""API-level tests for the auth endpoints.

Each test class maps to one or more SR-AUTH requirements from SEC-20260925-001.
The DB is mocked; all tests use the httpx AsyncClient fixture from conftest.py.

Note on rate limiting (SR-AUTH-007):
  The rate limiter uses X-Forwarded-For as the key. Tests that do NOT test rate
  limiting use unique synthetic IPs to avoid counter pollution between test runs.
  The rate-limiting test deliberately uses 6 requests from the same IP.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.engine.result import ScalarResult

from app.api.deps import _resolve_session, get_current_session
from app.db.models.auth import User, UserSession
from app.db.session import get_db
from app.main import app
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


def _unique_ip() -> str:
    """Return a unique synthetic IP to avoid rate-limiter counter pollution."""
    return f"10.0.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"


def _login_payload(email: str = TEST_EMAIL, password: str = TEST_PASSWORD) -> dict:
    return {"email": email, "password": password}


# ---------------------------------------------------------------------------
# SR-AUTH-001: Cookie attributes (HttpOnly, Secure, SameSite=Strict)
# ---------------------------------------------------------------------------

class TestCookieAttributes:
    @pytest.mark.asyncio
    async def test_login_sets_httponly_secure_samesite_strict(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=test_user)

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert resp.status_code == 200

        cookie_header = resp.headers.get("set-cookie", "")
        assert "session_token=" in cookie_header
        assert "httponly" in cookie_header.lower(), "HttpOnly flag missing"
        assert "secure" in cookie_header.lower(), "Secure flag missing"
        assert "samesite=strict" in cookie_header.lower(), "SameSite=Strict missing"

    @pytest.mark.asyncio
    async def test_login_sets_max_age_not_session_cookie(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=test_user)

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert "max-age=" in resp.headers.get("set-cookie", "").lower()


# ---------------------------------------------------------------------------
# SR-AUTH-002: CSRF — endpoints must reject non-JSON content types
# ---------------------------------------------------------------------------

class TestCSRFJsonOnly:
    @pytest.mark.asyncio
    async def test_form_urlencoded_login_is_rejected(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        """FastAPI/Pydantic rejects form data; only JSON bodies are accepted."""
        resp = await client.post(
            "/api/v1/auth/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"X-Forwarded-For": _unique_ip()},
        )
        # 422 Unprocessable Entity — Pydantic schema validation failure
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# SR-AUTH-004: Allowlist enforcement + email normalisation
# SR-AUTH-008: Identical error responses (no user enumeration)
# ---------------------------------------------------------------------------

class TestAllowlistAndEnumeration:
    @pytest.mark.asyncio
    async def test_non_allowlisted_email_returns_401(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", "other@example.com")

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_wrong_password_returns_same_error_as_missing_user(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SR-AUTH-008: error bodies must be identical for wrong pw and missing account."""
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)

        # Wrong password (user exists)
        override_db.scalar = AsyncMock(return_value=test_user)
        resp_wrong_pw = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(password="wrong_password"),
            headers={"X-Forwarded-For": _unique_ip()},
        )

        # Missing user (user does not exist in DB)
        override_db.scalar = AsyncMock(return_value=None)
        resp_missing = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(),
            headers={"X-Forwarded-For": _unique_ip()},
        )

        assert resp_wrong_pw.status_code == 401
        assert resp_missing.status_code == 401
        assert resp_wrong_pw.json() == resp_missing.json(), (
            "Error responses must be identical to prevent user enumeration"
        )

    @pytest.mark.asyncio
    async def test_uppercase_email_normalised_and_accepted(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SR-AUTH-004: ADMIN@EXAMPLE.COM should succeed when allowlist has admin@example.com."""
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=test_user)

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(email=TEST_EMAIL.upper()),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_email_with_whitespace_normalised(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=test_user)

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(email=f"  {TEST_EMAIL}  "),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_allowlist_denies_all(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SR-AUTH-004: ALLOWED_EMAILS='' must block all logins (fail-closed)."""
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", "")

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SR-AUTH-009: Logout completeness
# ---------------------------------------------------------------------------

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_deletes_session_from_db(
        self,
        override_db: AsyncMock,
        test_session: UserSession,
    ) -> None:
        """SR-AUTH-009: logout must delete the session row."""

        async def _mock_session() -> UserSession:
            return test_session

        app.dependency_overrides[get_current_session] = _mock_session
        try:
            async with AsyncClient(
                transport=__import__("httpx").ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                resp = await ac.post("/api/v1/auth/logout")

            assert resp.status_code == 200
            override_db.delete.assert_called_once_with(test_session)
            override_db.commit.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_current_session, None)

    @pytest.mark.asyncio
    async def test_logout_clears_session_cookie(
        self,
        override_db: AsyncMock,
        test_session: UserSession,
    ) -> None:
        """SR-AUTH-009: logout response must clear the session_token cookie."""

        async def _mock_session() -> UserSession:
            return test_session

        app.dependency_overrides[get_current_session] = _mock_session
        try:
            async with AsyncClient(
                transport=__import__("httpx").ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                resp = await ac.post("/api/v1/auth/logout")

            set_cookie = resp.headers.get("set-cookie", "")
            assert "session_token=" in set_cookie
            # Cookie cleared by setting max-age=0 or expiry in the past
            assert ("max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower())
        finally:
            app.dependency_overrides.pop(get_current_session, None)

    @pytest.mark.asyncio
    async def test_logout_without_session_returns_401(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        resp = await client.post("/api/v1/auth/logout")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# SR-AUTH-006: is_active checked on every request
# ---------------------------------------------------------------------------

class TestActiveUserCheck:
    @pytest.mark.asyncio
    async def test_me_without_cookie_returns_401(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_inactive_user_returns_401(
        self,
        override_db: AsyncMock,
        test_user: User,
        test_session: UserSession,
    ) -> None:
        """SR-AUTH-006: inactive users must be rejected at session validation time."""
        from sqlalchemy.engine import Result

        test_user.is_active = False
        test_session.user = test_user

        # _resolve_session queries for session WHERE is_active=True — returns None for inactive
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        override_db.execute = AsyncMock(return_value=mock_result)

        import hashlib, secrets
        raw = secrets.token_bytes(32)
        raw_hex = raw.hex()

        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=app),
            base_url="http://test",
            cookies={"session_token": raw_hex},
        ) as ac:
            resp = await ac.get("/api/v1/auth/me")

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_valid_session_returns_user(
        self,
        override_db: AsyncMock,
        test_user: User,
        test_session: UserSession,
    ) -> None:
        """SR-AUTH-006: active session returns user profile."""
        test_session.user = test_user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_session)
        override_db.execute = AsyncMock(return_value=mock_result)

        import secrets
        raw_hex = secrets.token_bytes(32).hex()

        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=app),
            base_url="http://test",
            cookies={"session_token": raw_hex},
        ) as ac:
            resp = await ac.get("/api/v1/auth/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == TEST_EMAIL
        assert data["id"] == 1


# ---------------------------------------------------------------------------
# SR-AUTH-007: Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_sixth_login_attempt_returns_429(
        self,
        override_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SR-AUTH-007: 6th attempt from same IP within window returns 429."""
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=None)  # always fail auth

        # Use a unique synthetic IP to avoid counter pollution from other tests
        test_ip = f"192.0.2.{uuid.uuid4().int % 200 + 1}"

        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            for attempt in range(5):
                resp = await ac.post(
                    "/api/v1/auth/login",
                    json=_login_payload(),
                    headers={"X-Forwarded-For": test_ip},
                )
                assert resp.status_code == 401, f"Attempt {attempt + 1} should be 401"

            # 6th attempt — should be rate limited
            resp = await ac.post(
                "/api/v1/auth/login",
                json=_login_payload(),
                headers={"X-Forwarded-For": test_ip},
            )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_retry_after_header_present_on_429(
        self,
        override_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SR-AUTH-007 GAP-001: Retry-After header must be present in 429 responses."""
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=None)

        test_ip = f"192.0.3.{uuid.uuid4().int % 200 + 1}"

        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            for _ in range(5):
                await ac.post(
                    "/api/v1/auth/login",
                    json=_login_payload(),
                    headers={"X-Forwarded-For": test_ip},
                )

            resp = await ac.post(
                "/api/v1/auth/login",
                json=_login_payload(),
                headers={"X-Forwarded-For": test_ip},
            )

        assert resp.status_code == 429
        assert "retry-after" in resp.headers, "Retry-After header must be present on 429"
        assert int(resp.headers["retry-after"]) > 0, "Retry-After value must be positive"

    @pytest.mark.asyncio
    async def test_successful_login_does_not_count_against_rate_limit(
        self,
        override_db: AsyncMock,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SR-AUTH-007 GAP-002: successful logins must not consume the failed-attempt budget."""
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=test_user)

        test_ip = f"192.0.4.{uuid.uuid4().int % 200 + 1}"

        async with AsyncClient(
            transport=__import__("httpx").ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            for attempt in range(5):
                resp = await ac.post(
                    "/api/v1/auth/login",
                    json=_login_payload(),
                    headers={"X-Forwarded-For": test_ip},
                )
                assert resp.status_code == 200, f"Successful login {attempt + 1} should be 200"

            # 6th successful login from the same IP must still succeed
            resp = await ac.post(
                "/api/v1/auth/login",
                json=_login_payload(),
                headers={"X-Forwarded-For": test_ip},
            )

        assert resp.status_code == 200, (
            "Successful logins must not count against the failed-attempt rate limit"
        )


# ---------------------------------------------------------------------------
# SR-AUTH-010: Secrets never in error responses or health endpoint
# ---------------------------------------------------------------------------

class TestSecretsSafety:
    @pytest.mark.asyncio
    async def test_health_returns_only_status(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        """SR-AUTH-010: health endpoint must not expose version, config, or secrets."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}, (
            "/health must return exactly {'status': 'ok'}"
        )

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_generic_body(self) -> None:
        """SR-AUTH-010: exception handler must not expose internals or stack traces.

        ServerErrorMiddleware always re-raises after sending the response so that
        ASGI servers can log the error — this is correct production behaviour but
        means the exception propagates through ASGITransport in tests.  We validate
        the handler contract directly instead of going through the full ASGI stack.
        """
        import json
        from unittest.mock import MagicMock

        from app.main import _unhandled_exception_handler

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/v1/auth/logout"

        exc = RuntimeError("secret internal error: SECRET_KEY=abc123")
        response = await _unhandled_exception_handler(request, exc)

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body == {"detail": "Internal server error"}
        assert "SECRET_KEY" not in response.body.decode()
        assert "abc123" not in response.body.decode()
        assert "Traceback" not in response.body.decode()


# ---------------------------------------------------------------------------
# SR-AUTH-012: Security headers on all responses
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_security_headers_on_health(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        resp = await client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_security_headers_on_login_response(
        self,
        client: AsyncClient,
        override_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("app.config.settings.ALLOWED_EMAILS", TEST_EMAIL)
        override_db.scalar = AsyncMock(return_value=None)

        resp = await client.post(
            "/api/v1/auth/login",
            json=_login_payload(),
            headers={"X-Forwarded-For": _unique_ip()},
        )
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    @pytest.mark.asyncio
    async def test_security_headers_on_401(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        resp = await client.get("/api/v1/auth/me")
        assert resp.headers.get("x-content-type-options") == "nosniff"


# ---------------------------------------------------------------------------
# SR-AUTH-013: CORS allow_headers not wildcard
# ---------------------------------------------------------------------------

class TestCORSHeaders:
    @pytest.mark.asyncio
    async def test_cors_allow_headers_not_wildcard(
        self, client: AsyncClient, override_db: AsyncMock
    ) -> None:
        """SR-AUTH-013: CORS allow_headers must not be '*'."""
        resp = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        # CORS preflight responds with allowed headers (when origin is permitted in dev)
        ach = resp.headers.get("access-control-allow-headers", "")
        assert ach != "*", "allow_headers must not be wildcard"


# ---------------------------------------------------------------------------
# SR-AUTH-011: .gitignore contains .env (file system check)
# ---------------------------------------------------------------------------

class TestGitignore:
    def test_gitignore_exists_and_excludes_env(self) -> None:
        """SR-AUTH-011: .env must never be committed."""
        import pathlib
        root = pathlib.Path(__file__).parent.parent.parent  # project root
        gitignore = root / ".gitignore"
        assert gitignore.exists(), ".gitignore must exist at project root"
        content = gitignore.read_text()
        assert ".env" in content, ".gitignore must contain .env entry"

    def test_env_example_has_no_real_secrets(self) -> None:
        """SR-AUTH-011: .env.example must not contain real credentials."""
        import pathlib
        env_example = pathlib.Path(__file__).parent.parent / ".env.example"
        assert env_example.exists(), ".env.example must exist"
        content = env_example.read_text()
        assert "CHANGE_ME" in content, ".env.example values must be placeholders"
        # These patterns look like real keys — the file should only have placeholders
        import re
        assert not re.search(r"sk-ant-[A-Za-z0-9]{10,}", content), \
            ".env.example must not contain a real Anthropic API key"
