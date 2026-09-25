━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Security Review — Phase 0 Auth (WEB-004)
ID:          SEC-20260925-001
Author:      Hanuman (Security Engineer)
Owner:       Atharva
Date:        2026-09-25
Version:     v1.0
Status:      Issued — pending Bhima implementation
References:  WEB-004, ARCH-20260923-001, IMP-20260923-001,
             app/config.py, app/db/models/auth.py, docs/schema.md
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Security Review — Phase 0 Authentication (WEB-004)

Scope: session-based login, allowlist enforcement, session/token handling,
CSRF protection, cookie security, password handling, and API-key exposure.

Not in scope: Phase 1+ features, infrastructure hardening (Nakula's domain),
frontend XSS (Arjun's domain).

---

## 1. What Was Reviewed

**Code files read:**
- `backend/app/config.py` — Settings, SECRET_KEY validation, ALLOWED_EMAILS parsing
- `backend/app/db/models/auth.py` — User and UserSession ORM models
- `backend/app/db/session.py` — Async/sync engine factories, get_db()
- `backend/app/main.py` — FastAPI shell, CORS config, docs gating
- `backend/app/db/base.py` — DeclarativeBase
- `docs/schema.md` — SQL DDL for users, sessions tables
- `docs/architecture.md` — System context diagram, container architecture, data flows
- `docs/implementation-plan.md` — WEB-004 requirements, agent roster

**Not yet written (under review as design intent):**
- Login endpoint (POST /auth/login)
- Session verification middleware / dependency
- Logout endpoint (POST /auth/logout)
- Password hashing code

---

## 2. Data Flow Diagram

```
                         ┌────────────────────────────────────────────┐
  TRUST BOUNDARY 1 ──►  │              Internet (attacker/user)       │
                         └──────────────────────┬─────────────────────┘
                                                │ HTTPS only
                         ┌──────────────────────▼─────────────────────┐
  TRUST BOUNDARY 2 ──►  │          Caddy reverse proxy (TLS)          │
                         └──────────────────────┬─────────────────────┘
                                                │ HTTP (localhost only)
                         ┌──────────────────────▼─────────────────────┐
                         │     FastAPI (Python process, port 8000)    │
                         │                                            │
                         │  ┌──────────────┐  ┌────────────────────┐ │
                         │  │ POST /auth/  │  │ Auth middleware    │ │
                         │  │   login      │  │ (session cookie    │ │
                         │  │   logout     │  │  verification)     │ │
                         │  └──────┬───────┘  └─────────┬──────────┘ │
                         │         │ parameterized SQL   │            │
  TRUST BOUNDARY 3 ──►  └─────────┼─────────────────────┼────────────┘
                                   │                     │
                         ┌─────────▼─────────────────────▼────────────┐
                         │        PostgreSQL (localhost only)          │
                         │  users table · sessions table               │
                         └────────────────────────────────────────────┘

  External (Phase 4+):
  FastAPI ──HTTPS──► Anthropic Claude API   (ANTHROPIC_API_KEY from env)
```

**Trust boundaries:**
1. Internet → Caddy: all traffic is hostile until authenticated
2. Browser → FastAPI (via Caddy): session cookie carries identity
3. FastAPI → PostgreSQL: trusted internal; DB accepts only localhost connections

---

## 3. STRIDE Threat Analysis

### 3.1 Login Endpoint (POST /auth/login)

| # | Threat | STRIDE | Likelihood | Impact | Rating |
|---|--------|--------|-----------|--------|--------|
| T-01 | Brute-force password guessing | Spoofing | High | High | **Critical** |
| T-02 | ALLOWED_EMAILS bypass via case mismatch | Spoofing | Medium | Critical | **Critical** |
| T-03 | User enumeration via timing difference | Information Disclosure | High | Low | Medium |
| T-04 | Account lockout bypass (no lockout exists) | Denial of Service (inverted) | High | High | **High** |
| T-05 | Session fixation: attacker plants a session token pre-login | Elevation of Privilege | Low | High | **High** |

### 3.2 Session Cookie

| # | Threat | STRIDE | Likelihood | Impact | Rating |
|---|--------|--------|-----------|--------|--------|
| T-06 | Session cookie theft via JavaScript (missing HttpOnly) | Information Disclosure | High | Critical | **Critical** |
| T-07 | Session cookie sent over HTTP (missing Secure flag) | Information Disclosure | Medium | Critical | **Critical** |
| T-08 | Session token with insufficient entropy | Spoofing | Low | Critical | **High** |
| T-09 | Long-lived session not invalidated on password change/logout | Elevation of Privilege | Medium | High | **High** |
| T-10 | CSRF: attacker forces state-changing request using victim's cookie | Tampering | High | High | **High** |

### 3.3 Allowlist Enforcement

| # | Threat | STRIDE | Likelihood | Impact | Rating |
|---|--------|--------|-----------|--------|--------|
| T-11 | Login email not lowercased before allowlist check | Spoofing | High | Critical | **Critical** |
| T-12 | `is_active` flag checked only at login, not on each request | Elevation of Privilege | Medium | High | **High** |
| T-13 | Allowlist empty string treated as "allow all" (misconfiguration) | Elevation of Privilege | Low | Critical | **High** |

### 3.4 Password Storage

| # | Threat | STRIDE | Likelihood | Impact | Rating |
|---|--------|--------|-----------|--------|--------|
| T-14 | Weak password hashing (not Argon2id / wrong parameters) | Information Disclosure | Medium | Critical | **Critical** |
| T-15 | Timing attack on password comparison | Spoofing | Low | High | Medium |

### 3.5 SECRET_KEY and API Keys

| # | Threat | STRIDE | Likelihood | Impact | Rating |
|---|--------|--------|-----------|--------|--------|
| T-16 | SECRET_KEY logged or exposed in error responses | Information Disclosure | Medium | Critical | **High** |
| T-17 | ANTHROPIC_API_KEY leaked via error message, log line, or health endpoint | Information Disclosure | Medium | High | **High** |
| T-18 | Secrets committed to version control via .env file | Information Disclosure | High | Critical | **Critical** |

### 3.6 Session Management

| # | Threat | STRIDE | Likelihood | Impact | Rating |
|---|--------|--------|-----------|--------|--------|
| T-19 | No mechanism to revoke all sessions (e.g. after suspected compromise) | Elevation of Privilege | Low | High | Medium |
| T-20 | SQL echo enabled in non-development environment | Information Disclosure | Low | High | Medium |
| T-21 | CORS `allow_headers=["*"]` if production origin ever added | Tampering | Low | Medium | Low |

---

## 4. Existing Strengths (Phase 0 Shell)

These controls are already correct and should be preserved in the auth implementation:

- `token_hash CHAR(64)`: the SHA-256 hash of the session token is stored, not the token itself — stolen DB row does not reveal a usable token.
- `ALLOWED_EMAILS` parsed to `frozenset` with `.lower()` — correct normalization direction.
- `SECRET_KEY` minimum 32-character validation enforced at startup.
- CORS `allow_origins=[]` in production — no cross-origin API access by default.
- `/docs` and `/redoc` disabled in production.
- `is_active` field present on User — deactivation mechanism exists at schema level.
- `ip_address INET` + `user_agent` on sessions — audit trail for forensics.
- `ON DELETE CASCADE` on sessions — user deletion cleans up tokens.
- `.env.example` has `SECRET_KEY` generation guidance (`secrets.token_hex(32)`).
- `ANTHROPIC_API_KEY` defaults to empty string — LLM calls fail explicitly rather than silently using a wrong key.
- `pool_pre_ping=True` on both engines — stale connections recycled without exposing errors.

---

## 5. Security Requirements for Bhima

The following requirements must be implemented in the auth shell. Bhima may not ship WEB-004 without meeting every Critical and High requirement. Medium requirements are recommended before Phase 1 exit.

---

### SR-AUTH-001 — Session Cookie Attributes

**Component:** POST /auth/login → Set-Cookie response header  
**Threats mitigated:** T-06 (XSS cookie theft), T-07 (HTTP interception)  
**Priority:** Critical  
**Owner:** Bhima  

**Requirement:**  
The session token cookie MUST be set with all three security attributes:
`HttpOnly`, `Secure`, and `SameSite=Strict`.

```python
# Required Set-Cookie header for the session token
response.set_cookie(
    key="session_token",
    value=raw_token,          # the raw token, NOT the hash
    httponly=True,             # blocks JavaScript document.cookie access
    secure=True,               # HTTPS only; Caddy terminates TLS
    samesite="strict",         # blocks cross-origin cookie sends (CSRF mitigation)
    max_age=SESSION_EXPIRE_DAYS * 86400,
    path="/",
)
```

`SameSite=Strict` means the cookie is not sent on any cross-site request,
including navigation from external links. For a private personal tool this is
acceptable; it means a bookmark click from an email will require a login.
`SameSite=Lax` is the alternative if cross-site navigation with session must
work — but it reduces CSRF protection.

**Acceptance Criteria:**
- [ ] `Set-Cookie` response after successful login includes `HttpOnly` flag
- [ ] `Set-Cookie` response after successful login includes `Secure` flag
- [ ] `Set-Cookie` response after successful login includes `SameSite=Strict`
- [ ] `document.cookie` in browser dev tools does NOT show the session cookie after login
- [ ] Session cookie is not transmitted on HTTP requests (Caddy enforces HTTPS; verify with test)
- [ ] `max_age` is set to `SESSION_EXPIRE_DAYS × 86400` seconds (not a session cookie, which would expire on browser close)

---

### SR-AUTH-002 — CSRF Protection

**Component:** All state-changing API endpoints  
**Threats mitigated:** T-10  
**Priority:** High  
**Owner:** Bhima  

**Requirement:**  
`SameSite=Strict` on the session cookie (SR-AUTH-001) is the primary CSRF
defence for a same-origin frontend. No additional CSRF token is required
provided SameSite=Strict is enforced without exception.

However: if any endpoint ever accepts `Content-Type: application/x-www-form-urlencoded`
(browser form submissions), a secondary CSRF token MUST be added to that endpoint,
because form-based cross-origin requests are not blocked by SameSite=Strict in all
browser versions.

**Acceptance Criteria:**
- [ ] All auth and data-mutation endpoints use `Content-Type: application/json` — not form-urlencoded
- [ ] Verify: `curl -X POST http://localhost:8000/auth/login -d "email=...&password=..."` returns 422 (FastAPI rejects non-JSON body by default with Pydantic models — confirm this is wired correctly)
- [ ] If a form-based endpoint is ever added, a double-submit cookie CSRF token is implemented

---

### SR-AUTH-003 — Session Fixation Prevention

**Component:** POST /auth/login  
**Threats mitigated:** T-05  
**Priority:** High  
**Owner:** Bhima  

**Requirement:**  
A new session token MUST be generated on every successful login. Any
pre-existing session with the same browser (if there is one from a prior
unauthenticated step) must be invalidated before issuing the new one.
The login endpoint must never accept or promote a client-supplied token.

The session token MUST be generated server-side with `secrets.token_bytes(32)`
(yielding 256 bits of entropy). Do not use UUIDs (only 122 bits of randomness).

```python
import secrets
raw_token = secrets.token_bytes(32)
token_hash = hashlib.sha256(raw_token).hexdigest()  # stored in DB
cookie_value = raw_token.hex()                       # sent to browser
```

**Acceptance Criteria:**
- [ ] Each successful login creates a new row in `sessions` with a freshly generated token
- [ ] Login endpoint does not accept a `session_token` parameter in the request body or query string
- [ ] `secrets.token_bytes(32)` (or equivalent 256-bit source) is used — UUID or `random` module is not used
- [ ] `token_hash = sha256(raw_token)` — the stored hash matches the pattern `[0-9a-f]{64}`

---

### SR-AUTH-004 — Allowlist Enforcement (Case Normalization)

**Component:** POST /auth/login — allowlist check  
**Threats mitigated:** T-11, T-13  
**Priority:** Critical  
**Owner:** Bhima  

**Requirement:**  
The user-supplied login email MUST be normalized to lowercase before the
allowlist check AND before the database lookup. The current `allowed_emails_set`
property correctly stores lowercase values, but the check only works if the
input is also lowercased first.

The check must happen at two points:
1. Before the allowlist gate (reject non-allowlisted emails before any DB query)
2. When fetching the user from the DB (query by `email.lower()`)

```python
# Correct pattern
incoming_email = request_body.email.strip().lower()
if incoming_email not in settings.allowed_emails_set:
    raise HTTPException(status_code=403, detail="Access denied")
user = await db.scalar(select(User).where(User.email == incoming_email))
```

Additionally: if `ALLOWED_EMAILS` is not set in the environment, the allowlist is
empty and NO login is possible. This is correct fail-closed behavior. Bhima must
not add a fallback that opens access when the env var is absent.

**Acceptance Criteria:**
- [ ] Login attempt with `ADMIN@example.com` is rejected when allowlist contains only `admin@example.com`
- [ ] Login attempt with `admin@EXAMPLE.COM` is rejected under the same condition
- [ ] Login attempt with `  admin@example.com  ` (leading/trailing spaces) is rejected or normalized correctly
- [ ] When `ALLOWED_EMAILS=""` in the environment, no login succeeds regardless of credentials
- [ ] Allowlist check occurs BEFORE any password comparison (fail fast, avoid timing oracle)

---

### SR-AUTH-005 — Password Hashing (Argon2id)

**Component:** User creation + POST /auth/login  
**Threats mitigated:** T-14, T-15  
**Priority:** Critical  
**Owner:** Bhima  

**Requirement:**  
Passwords MUST be hashed with Argon2id using `argon2-cffi`. The OWASP-recommended
minimum parameters (2025) are:

```python
# argon2-cffi PasswordHasher defaults are acceptable:
# m=65536 (64 MiB memory), t=3 (time cost), p=4 (parallelism)
# These match OWASP guidance. Do NOT reduce memory below 19456 (19 MiB).
from argon2 import PasswordHasher
ph = PasswordHasher()  # uses defaults; acceptable

# Store
hashed = ph.hash(plaintext_password)

# Verify — argon2-cffi uses constant-time comparison internally
try:
    ph.verify(stored_hash, plaintext_password)
except argon2.exceptions.VerifyMismatchError:
    # wrong password
except argon2.exceptions.VerificationError:
    # hash format error
```

`ph.check_needs_rehash(stored_hash)` should be called after a successful login.
If True, re-hash and update the stored hash in the same transaction as the
session creation.

**Acceptance Criteria:**
- [ ] `hashed_password` column values start with `$argon2id$` — never `$2b$` (bcrypt) or plain text
- [ ] `argon2-cffi` is the hashing library — not hashlib.sha256, bcrypt, or passlib
- [ ] Verify call uses argon2-cffi's built-in comparison, not a custom `==` comparison
- [ ] Memory parameter is ≥19456 KiB in the PasswordHasher configuration
- [ ] Password rehashing logic runs on successful login when `check_needs_rehash` returns True

---

### SR-AUTH-006 — `is_active` Checked on Every Authenticated Request

**Component:** Auth middleware / session verification dependency  
**Threats mitigated:** T-12  
**Priority:** High  
**Owner:** Bhima  

**Requirement:**  
The session verification dependency (the FastAPI `Depends(get_current_user)` pattern)
MUST check `user.is_active` on every request, not only at login time. An existing valid
session token must be rejected if the user's `is_active` flag is False.

The DB query in the middleware must join or re-fetch the User record — it must not
rely on data cached from the login step.

```python
async def get_current_user(
    session_token: str = Cookie(...),
    db: AsyncSession = Depends(get_db),
) -> User:
    token_hash = hashlib.sha256(bytes.fromhex(session_token)).hexdigest()
    session = await db.scalar(
        select(UserSession)
        .join(User)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > func.now(),
            User.is_active.is_(True),   # ← required
        )
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session.user
```

**Acceptance Criteria:**
- [ ] Setting `users.is_active = FALSE` for a user via direct DB update causes their next request to return 401
- [ ] The user does NOT need to log out and back in for the deactivation to take effect
- [ ] `user.is_active` check is in the session verification query — not in a separate call that could race

---

### SR-AUTH-007 — Brute Force Protection

**Component:** POST /auth/login  
**Threats mitigated:** T-01, T-04  
**Priority:** High  
**Owner:** Bhima  

**Requirement:**  
The login endpoint MUST implement rate limiting. For a personal tool exposed
on Oracle Cloud, a simple in-process rate limiter on IP address is sufficient.

Minimum requirement: exponential backoff response time after 5 failed attempts
from the same IP within a 10-minute window.

The recommended approach for a single-process FastAPI deployment is
`slowapi` (Starlette middleware, backed by in-memory counter):

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/auth/login")
@limiter.limit("5/10minute")   # 5 login attempts per 10 minutes per IP
async def login(request: Request, ...):
    ...
```

Note: `slowapi` in-process counters reset on process restart. For this
personal-use deployment this is acceptable. Add `slowapi` to `pyproject.toml`.

**Acceptance Criteria:**
- [ ] The 6th failed login attempt from the same IP within 10 minutes returns 429 Too Many Requests
- [ ] A successful login attempt does NOT count against the rate limit
- [ ] The `Retry-After` header is set in the 429 response
- [ ] Rate limiting applies per IP, not per email — prevents enumeration of which emails get locked

---

### SR-AUTH-008 — Login Response Timing (User Enumeration)

**Component:** POST /auth/login  
**Threats mitigated:** T-03  
**Priority:** Medium  
**Owner:** Bhima  

**Requirement:**  
The login endpoint MUST take a constant amount of time regardless of whether
the email exists in the database. If the email is not found, a dummy Argon2id
verification call must still be performed to prevent timing-based user enumeration.

```python
# When email not found in DB, still run a dummy verify to equalize timing
DUMMY_HASH = ph.hash("dummy_password_for_timing_normalization")

async def login(...):
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        ph.verify(DUMMY_HASH, body.password)   # timing equalizer — always raises
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        ph.verify(user.hashed_password, body.password)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
```

Return identical error messages for "email not found" and "wrong password":
`"Invalid credentials"` — not `"User not found"` or `"Wrong password"`.

**Acceptance Criteria:**
- [ ] Login with a non-existent email and login with wrong password return identical response bodies
- [ ] Login with a non-existent email and correct password return 401 (not 404)
- [ ] A dummy hash call is present in the "email not found" code path (code review)

---

### SR-AUTH-009 — Logout Completeness

**Component:** POST /auth/logout  
**Threats mitigated:** T-09  
**Priority:** High  
**Owner:** Bhima  

**Requirement:**  
Logout MUST:
1. Delete the session row from the `sessions` table (server-side invalidation)
2. Clear the session cookie in the response (client-side removal)

Both steps are required. Clearing only the cookie leaves the token valid in the
DB (replay attack). Deleting only the DB row leaves the cookie in the browser.

```python
@app.post("/auth/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    session: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(session)
    await db.commit()
    response.delete_cookie(key="session_token", httponly=True, secure=True, samesite="strict")
    return {"status": "logged_out"}
```

**Acceptance Criteria:**
- [ ] After logout, the session row is absent from the `sessions` table
- [ ] After logout, the `session_token` cookie is absent in the browser
- [ ] Replaying the old session token after logout returns 401
- [ ] Logout endpoint requires authentication (anonymous logout returns 401)

---

### SR-AUTH-010 — Secrets Never Logged or Exposed

**Component:** Application-wide — config, error handlers, middleware  
**Threats mitigated:** T-16, T-17  
**Priority:** High  
**Owner:** Bhima  

**Requirement:**  
The following values MUST never appear in log output, error response bodies,
or HTTP headers, under any circumstances:

- `SECRET_KEY`
- `ANTHROPIC_API_KEY`
- `DATABASE_URL` (contains DB password)
- `session_token` cookie values
- `token_hash` values
- Any Argon2id hash string (`$argon2id$...`)

**Specific rules:**

1. FastAPI's default exception handler must not return stack traces in production.
   Set `app = FastAPI(debug=False)` explicitly (not relying on the default) and
   install a custom exception handler that returns a generic error body.

2. SQLAlchemy `echo=settings.is_development` is already correct — do not change this.
   Verify that `ENVIRONMENT` defaults to `"production"` (it does in the current config).

3. `settings` object must not be serialized into any response. If you need to
   expose config values (e.g. feature flags), create an explicit allowlist of
   fields that are safe to expose.

4. The `ANTHROPIC_API_KEY` validation — add a startup check that the key format is
   valid (starts with `sk-ant-`) when the key is non-empty, without logging the key value.

**Acceptance Criteria:**
- [ ] A deliberately triggered 500 error returns `{"detail": "Internal server error"}` in production — no stack trace, no file path, no variable values
- [ ] Grep of application log output contains no match for `SECRET_KEY=`, `sk-ant-`, or `$argon2id$`
- [ ] `GET /health` response body contains only `{"status": "ok"}` — no version, build info, or config values
- [ ] Code review confirms `settings.SECRET_KEY` is not referenced in any log statement

---

### SR-AUTH-011 — .env File Never Committed

**Component:** Version control configuration  
**Threats mitigated:** T-18  
**Priority:** Critical  
**Owner:** Bhima  

**Requirement:**  
`.env` must be in `.gitignore` before any commit is made to the repository.
`.env.example` (without real values) is committed instead.

This is pre-implementation — it applies to the first git commit of this project.

```gitignore
# .gitignore (must include)
.env
*.env
.env.*
!.env.example
```

**Acceptance Criteria:**
- [ ] `.gitignore` contains `.env`
- [ ] `git ls-files | grep -E "^\.env$"` returns empty
- [ ] `.env.example` is committed with placeholder values only
- [ ] `git log --all --oneline -- .env` returns empty (no historical commits of .env)

---

### SR-AUTH-012 — HTTP Security Headers

**Component:** Caddy reverse proxy + FastAPI middleware  
**Threats mitigated:** General hardening — XSS, clickjacking, MIME sniffing  
**Priority:** Medium  
**Owner:** Bhima (FastAPI headers) + Nakula (Caddy config)  

**Requirement:**  
The following headers MUST be present on all API responses. Bhima adds them
via FastAPI middleware; Nakula adds them in the Caddy config for the Next.js
frontend. This requirement covers the API layer only.

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # HSTS is set by Caddy for HTTPS — no need to duplicate here
        return response
```

**Acceptance Criteria:**
- [ ] `X-Content-Type-Options: nosniff` present on all API responses
- [ ] `X-Frame-Options: DENY` present on all API responses
- [ ] `Referrer-Policy: strict-origin-when-cross-origin` present on all API responses

Hanuman to Nakula: please add `Strict-Transport-Security: max-age=31536000; includeSubDomains`
in the Caddy config at the TLS termination point.

---

### SR-AUTH-013 — CORS: Restrict Allowed Headers in Production

**Component:** `app/main.py` — CORSMiddleware  
**Threats mitigated:** T-21  
**Priority:** Low (addressed now while the config is small)  
**Owner:** Bhima  

**Requirement:**  
Replace `allow_headers=["*"]` with an explicit allowlist in the CORSMiddleware
configuration. Even though `allow_origins=[]` in production currently means
CORS is effectively closed, this prevents silent regression if a production
origin is added later.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Accept"],   # was ["*"]
)
```

**Acceptance Criteria:**
- [ ] `allow_headers` does not contain `"*"`
- [ ] `Content-Type` and `Accept` are in the allowlist
- [ ] No legitimate frontend request (login, logout, data fetch) fails after this change

---

## 6. Requirements Summary Table

| SR-ID | Description | Priority | Owner | Threats |
|---|---|---|---|---|
| SR-AUTH-001 | Cookie: HttpOnly + Secure + SameSite=Strict | **Critical** | Bhima | T-06, T-07 |
| SR-AUTH-002 | CSRF: SameSite=Strict + JSON-only endpoints | **High** | Bhima | T-10 |
| SR-AUTH-003 | Session fixation: new token per login, 256-bit entropy | **High** | Bhima | T-05, T-08 |
| SR-AUTH-004 | Allowlist: lowercase normalize input before check | **Critical** | Bhima | T-11, T-13 |
| SR-AUTH-005 | Password: Argon2id via argon2-cffi, OWASP params | **Critical** | Bhima | T-14, T-15 |
| SR-AUTH-006 | `is_active` checked on every request (not only login) | **High** | Bhima | T-12 |
| SR-AUTH-007 | Rate limiting: 5 attempts / 10 min / IP (slowapi) | **High** | Bhima | T-01, T-04 |
| SR-AUTH-008 | Timing normalization: dummy Argon2 on missing email | **Medium** | Bhima | T-03 |
| SR-AUTH-009 | Logout: DB row deleted + cookie cleared | **High** | Bhima | T-09 |
| SR-AUTH-010 | Secrets: never logged, never in error responses | **High** | Bhima | T-16, T-17 |
| SR-AUTH-011 | `.env` in `.gitignore` before first commit | **Critical** | Bhima | T-18 |
| SR-AUTH-012 | Security headers: X-Content-Type-Options, X-Frame-Options | **Medium** | Bhima + Nakula | General |
| SR-AUTH-013 | CORS: explicit `allow_headers` allowlist | **Low** | Bhima | T-21 |

**Critical count: 5. High count: 6. Medium count: 2. Low count: 1.**

---

## 7. Out of Scope (Noted for Future Phases)

- **WEB-004 Phase 1+:** MFA is not required for a personal-use tool where the
  allowlist is a single email. Revisit if multi-user access is ever added.
- **Session listing UI:** Not required for Phase 0 but recommended for Phase 5+
  (WEB-012 admin area). A `GET /auth/sessions` endpoint listing active sessions
  with creation time, last-seen, and a revoke button would give the owner visibility.
- **HSTS preloading:** Nakula to set `max-age=31536000; includeSubDomains` in
  Caddy. Preload registration is optional and irreversible — deferred.
- **Mutual TLS (mTLS):** Between Next.js and FastAPI (localhost). Not warranted
  for a localhost-only interface.
- **CSP on the frontend:** Arjun's domain. Hanuman recommends a restrictive policy
  (`default-src 'self'`) for Phase 1.
- **ANTHROPIC_API_KEY rotation:** Key rotation procedure should be documented
  before Phase 4 when LLM calls become active.

---

## 8. Dependency Addition Required

Add `slowapi` to `backend/pyproject.toml` before implementing SR-AUTH-007.

```toml
# In [project.dependencies]
"slowapi>=0.1.9",
```

`argon2-cffi` is already in `pyproject.toml` — confirm it is `argon2-cffi >= 23.1.0`.

---

## 9. Acceptance Testing Handoff to Sahadeva

When Bhima marks WEB-004 as ready for QA, Sahadeva must independently verify
every acceptance criterion in §5 above. Particular attention to:

- SR-AUTH-001: cookie flags (browser dev tools + `curl -v`)
- SR-AUTH-004: case mismatch login attempts
- SR-AUTH-005: `$argon2id$` hash prefix in DB
- SR-AUTH-006: `is_active = FALSE` does not require logout to take effect
- SR-AUTH-009: session row gone from DB after logout
- SR-AUTH-010: 500-response body in production mode
- SR-AUTH-011: `git ls-files | grep .env` returns empty

---

*SEC-20260925-001 · v1.0 · Hanuman · Issued · 2026-09-25*
*Implementation: Bhima (auth shell) · QA: Sahadeva · Infrastructure: Nakula (HSTS header)*
