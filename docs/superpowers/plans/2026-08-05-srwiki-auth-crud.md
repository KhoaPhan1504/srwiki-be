# SR-WIKI Auth CRUD Starter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap SR-WIKI: a FastAPI backend on Supabase (Auth + Postgres) and a React (Vite+TS) frontend, with register/login/profile-CRUD/phone-OTP/delete-account, a Dashboard behind a right-side nav, and Docker + Netlify/Render deployment scaffolding.

**Architecture:** React FE (Vite/TS/Tailwind, company conventions: axios+interceptors, Jotai, React Query, `~root/*` alias) talks only to the FastAPI BE over Bearer-token REST. The BE holds all Supabase credentials; it uses the caller's own access token (RLS-respecting) for profile reads/writes and the service-role key only for admin-only operations (delete user). Full design rationale is in [docs/superpowers/specs/2026-08-05-srwiki-auth-crud-design.md](../specs/2026-08-05-srwiki-auth-crud-design.md).

**Tech Stack:** Python 3.12, FastAPI, supabase-py, phonenumbers, pytest; React 18, Vite, TypeScript, Tailwind CSS, React Router v6, @tanstack/react-query, Jotai, axios, react-toastify, react-phone-number-input; Docker, Netlify, Render/Railway (prep only).

## Global Constraints

- Frontend never calls Supabase directly — all Auth/data operations go through the FastAPI backend; the service-role key never leaves the backend.
- Profile reads/writes use the caller's own Supabase access token (`user_client`, RLS-respecting), never the service-role key. Service-role (`admin_client`) is reserved for `auth.admin.*` operations and system-initiated bootstrap writes (creating the profile row at registration).
- `profiles.phone` / `profiles.phone_verified` are written only by the OTP verify endpoint. `PUT /profile` must never accept a `phone` field (`ProfileUpdateRequest` uses `extra="forbid"`).
- OTP codes: 6 digits, 5-minute expiry, dev-mode `debug_otp` field returned only when `OTP_DEBUG_MODE=true`.
- Phone numbers are validated server-side with `phonenumbers` against the E.164 string the client sends — the backend never trusts client-side validation alone.
- All JSON response bodies are flat objects, no `{data: ...}` envelope — e.g. auth endpoints return `{token, refreshToken, user}` directly.
- Frontend path alias: `~root/*` → `src/*`.
- Frontend default phone country: Vietnam (`+84`).
- Frontend automated testing is out of scope for this pass; `npm run build` + `npm run lint` are the quality gate for every FE task.
- `.env` is gitignored in both `srwiki-be/` and `srwiki-fe/`; `.env.template` is committed with placeholder values only.

---

## Phase A — Backend (`srwiki-be/`)

### Task 1: Backend scaffold — config, health check, test harness

**Files:**
- Create: `srwiki-be/requirements.txt`, `srwiki-be/requirements-dev.txt`, `srwiki-be/.env.template`, `srwiki-be/.gitignore`
- Create: `srwiki-be/app/__init__.py`, `srwiki-be/app/config.py`, `srwiki-be/app/main.py`
- Create: `srwiki-be/tests/__init__.py`, `srwiki-be/tests/conftest.py`, `srwiki-be/tests/test_config.py`, `srwiki-be/tests/test_health.py`
- Modify: remove `srwiki-be/main.py` (stale PyCharm sample, superseded by `app/main.py`)

**Interfaces:**
- Produces: `app.config.Settings` (fields: `supabase_url`, `supabase_anon_key`, `supabase_service_role_key`, `otp_debug_mode: bool`, `cors_origins: str`, property `cors_origins_list: list[str]`), `app.config.get_settings() -> Settings` (lru_cached), `app.main.app` (FastAPI instance), `app.main.create_app() -> FastAPI`.

- [ ] **Step 1: Create the backend directory skeleton**

The git repository for the whole project is rooted at `SR-WIKI/` (one level up
from `srwiki-be/`) and already exists by the time this task runs, as does the
isolated worktree this task executes in.

```bash
mkdir -p srwiki-be/app srwiki-be/tests
cd srwiki-be
touch app/__init__.py tests/__init__.py
```

- [ ] **Step 2: Write `requirements.txt`**

```
fastapi>=0.115,<0.116
uvicorn[standard]>=0.32,<0.33
supabase>=2.9,<3.0
pydantic>=2.9,<3.0
pydantic-settings>=2.6,<3.0
email-validator>=2.2,<3.0
phonenumbers>=8.13,<9.0
python-dotenv>=1.0,<2.0
```

- [ ] **Step 3: Write `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.3,<9.0
pytest-mock>=3.14,<4.0
httpx>=0.27,<0.28
```

- [ ] **Step 4: Write `.env.template`**

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
OTP_DEBUG_MODE=true
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 5: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
```

- [ ] **Step 6: Create a venv and install dependencies**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

- [ ] **Step 7: Write the failing test for settings parsing**

`srwiki-be/tests/conftest.py`:

```python
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("OTP_DEBUG_MODE", "true")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")
```

`srwiki-be/tests/test_config.py`:

```python
from app.config import get_settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://foo.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, http://localhost:3000")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.supabase_url == "https://foo.supabase.co"
    assert settings.cors_origins_list == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    get_settings.cache_clear()
```

- [ ] **Step 8: Run it to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 9: Implement `app/config.py`**

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    otp_debug_mode: bool = True
    cors_origins: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 10: Run the test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 11: Write the failing health-check test**

`srwiki-be/tests/test_health.py`:

```python
from fastapi.testclient import TestClient
from app.main import app


def test_health_check():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 12: Run it to verify it fails**

Run: `pytest tests/test_health.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 13: Implement `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SR-WIKI API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 14: Run the full test suite to verify it passes**

Run: `pytest -v`
Expected: PASS (both test_config.py and test_health.py)

- [ ] **Step 15: Commit**

```bash
git add requirements.txt requirements-dev.txt .env.template .gitignore app tests
git rm main.py
git commit -m "chore: scaffold FastAPI backend with config and health check"
```

---

### Task 2: Supabase client wrappers

**Files:**
- Create: `srwiki-be/app/supabase_client.py`
- Test: `srwiki-be/tests/test_supabase_client.py`

**Interfaces:**
- Consumes: `app.config.get_settings` (Task 1)
- Produces: `app.supabase_client.anon_client() -> Client` (lru_cached), `app.supabase_client.admin_client() -> Client` (lru_cached), `app.supabase_client.user_client(access_token: str) -> Client` (not cached; calls `client.postgrest.auth(access_token)` before returning)

- [ ] **Step 1: Write the failing tests**

```python
# srwiki-be/tests/test_supabase_client.py
from unittest.mock import MagicMock
import app.supabase_client as sc
from app.config import get_settings


def test_anon_client_uses_anon_key(mocker):
    sc.anon_client.cache_clear()
    fake_client = MagicMock()
    mock_create = mocker.patch("app.supabase_client.create_client", return_value=fake_client)

    result = sc.anon_client()

    settings = get_settings()
    mock_create.assert_called_once_with(settings.supabase_url, settings.supabase_anon_key)
    assert result is fake_client
    sc.anon_client.cache_clear()


def test_admin_client_uses_service_role_key(mocker):
    sc.admin_client.cache_clear()
    fake_client = MagicMock()
    mock_create = mocker.patch("app.supabase_client.create_client", return_value=fake_client)

    result = sc.admin_client()

    settings = get_settings()
    mock_create.assert_called_once_with(settings.supabase_url, settings.supabase_service_role_key)
    assert result is fake_client
    sc.admin_client.cache_clear()


def test_user_client_attaches_access_token(mocker):
    fake_client = MagicMock()
    mocker.patch("app.supabase_client.create_client", return_value=fake_client)

    result = sc.user_client("token-123")

    fake_client.postgrest.auth.assert_called_once_with("token-123")
    assert result is fake_client
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_supabase_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.supabase_client'`

- [ ] **Step 3: Implement `app/supabase_client.py`**

```python
from functools import lru_cache
from supabase import create_client, Client
from app.config import get_settings


@lru_cache
def anon_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache
def admin_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def user_client(access_token: str) -> Client:
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_supabase_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/supabase_client.py tests/test_supabase_client.py
git commit -m "feat: add Supabase client wrappers for anon/admin/per-user access"
```

---

### Task 3: Pydantic schemas + phone validation

**Files:**
- Create: `srwiki-be/app/schemas.py`, `srwiki-be/app/phone.py`
- Test: `srwiki-be/tests/test_schemas.py`, `srwiki-be/tests/test_phone.py`

**Interfaces:**
- Produces: `app.schemas.{RegisterRequest, LoginRequest, RefreshRequest, UserOut, AuthResponse, ProfileOut, ProfileUpdateRequest, SendOtpRequest, VerifyOtpRequest}`; `app.phone.validate_phone_e164(phone: str) -> str`, `app.phone.InvalidPhoneNumberError(ValueError)`

- [ ] **Step 1: Write the failing schema tests**

```python
# srwiki-be/tests/test_schemas.py
import pytest
from pydantic import ValidationError
from app.schemas import RegisterRequest, ProfileUpdateRequest


def test_register_request_accepts_valid_data():
    req = RegisterRequest(email="a@b.com", password="password123", full_name="A B")
    assert req.email == "a@b.com"


def test_register_request_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.com", password="short", full_name="A B")


def test_register_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="password123", full_name="A B")


def test_profile_update_request_rejects_phone_field():
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(phone="+84912345678")
```

- [ ] **Step 2: Write the failing phone validation tests**

```python
# srwiki-be/tests/test_phone.py
import pytest
from app.phone import validate_phone_e164, InvalidPhoneNumberError


def test_valid_vietnam_number_returns_e164():
    assert validate_phone_e164("+84912345678") == "+84912345678"


def test_missing_plus_prefix_is_rejected():
    with pytest.raises(InvalidPhoneNumberError):
        validate_phone_e164("0912345678")


def test_garbage_input_is_rejected():
    with pytest.raises(InvalidPhoneNumberError):
        validate_phone_e164("+1234")
```

- [ ] **Step 3: Run to verify both fail**

Run: `pytest tests/test_schemas.py tests/test_phone.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `app/phone.py`**

```python
import phonenumbers


class InvalidPhoneNumberError(ValueError):
    pass


def validate_phone_e164(phone: str) -> str:
    try:
        parsed = phonenumbers.parse(phone, None)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumberError(str(exc)) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumberError(f"'{phone}' is not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
```

- [ ] **Step 5: Implement `app/schemas.py`**

```python
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refreshToken: str


class UserOut(BaseModel):
    id: str
    email: EmailStr


class AuthResponse(BaseModel):
    token: str
    refreshToken: str
    user: UserOut


class ProfileOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None
    phone_verified: bool = False
    address: str | None = None
    date_of_birth: date | None = None
    created_at: datetime
    updated_at: datetime


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, min_length=1)
    address: str | None = None
    date_of_birth: date | None = None


class SendOtpRequest(BaseModel):
    phone: str


class VerifyOtpRequest(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)
```

- [ ] **Step 6: Run to verify both pass**

Run: `pytest tests/test_schemas.py tests/test_phone.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/schemas.py app/phone.py tests/test_schemas.py tests/test_phone.py
git commit -m "feat: add request/response schemas and E.164 phone validation"
```

---

### Task 4: Auth dependency (`get_current_user`)

**Files:**
- Create: `srwiki-be/app/dependencies.py`
- Test: `srwiki-be/tests/test_dependencies.py`

**Interfaces:**
- Consumes: `app.supabase_client.admin_client` (Task 2)
- Produces: `app.dependencies.get_current_user(authorization: str | None) -> dict` with keys `id`, `email`, `access_token` — raises `HTTPException(401)` on missing/invalid token. This is the dependency every protected route in later tasks uses via `Depends(get_current_user)`.

- [ ] **Step 1: Write the failing tests**

```python
# srwiki-be/tests/test_dependencies.py
from types import SimpleNamespace
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from app.dependencies import get_current_user

app = FastAPI()


@app.get("/whoami")
def whoami(current_user: dict = Depends(get_current_user)):
    return current_user


client = TestClient(app)


def test_missing_authorization_header_returns_401():
    response = client.get("/whoami")
    assert response.status_code == 401


def test_invalid_token_returns_401(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    mock_admin.return_value.auth.get_user.side_effect = Exception("invalid jwt")

    response = client.get("/whoami", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401


def test_valid_token_returns_user(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    fake_user = SimpleNamespace(id="user-1", email="a@b.com")
    mock_admin.return_value.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.get("/whoami", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json() == {"id": "user-1", "email": "a@b.com", "access_token": "good-token"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_dependencies.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.dependencies'`

- [ ] **Step 3: Implement `app/dependencies.py`**

```python
from fastapi import Header, HTTPException
from app.supabase_client import admin_client


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        response = admin_client().auth.get_user(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = getattr(response, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"id": user.id, "email": user.email, "access_token": token}
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_dependencies.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/dependencies.py tests/test_dependencies.py
git commit -m "feat: add get_current_user dependency for Bearer token auth"
```

---

### Task 5: Auth router — register, login, refresh, logout

**Files:**
- Create: `srwiki-be/app/routers/__init__.py`, `srwiki-be/app/routers/auth.py`
- Test: `srwiki-be/tests/test_auth_router.py`

**Interfaces:**
- Consumes: `app.schemas.{RegisterRequest, LoginRequest, RefreshRequest, AuthResponse, UserOut}` (Task 3), `app.supabase_client.{anon_client, admin_client}` (Task 2), `app.dependencies.get_current_user` (Task 4)
- Produces: `app.routers.auth.router` (FastAPI `APIRouter`, prefix `/auth`) with routes `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`

- [ ] **Step 1: Write the failing tests**

```python
# srwiki-be/tests/test_auth_router.py
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import auth

app = FastAPI()
app.include_router(auth.router)
client = TestClient(app)


def test_register_success(mocker):
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"), session=None
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "full_name": "A B"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": "user-1", "email": "a@b.com"}
    fake_admin.table.return_value.insert.assert_called_once_with(
        {"id": "user-1", "full_name": "A B"}
    )


def test_register_rolls_back_user_when_profile_insert_fails(mocker):
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"), session=None
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)
    fake_admin = mocker.MagicMock()
    fake_admin.table.return_value.insert.return_value.execute.side_effect = Exception("db error")
    mocker.patch("app.routers.auth.admin_client", return_value=fake_admin)

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "full_name": "A B"},
    )

    assert response.status_code == 500
    fake_admin.auth.admin.delete_user.assert_called_once_with("user-1")


def test_register_failure_returns_400(mocker):
    fake_anon = mocker.MagicMock()
    fake_anon.auth.sign_up.side_effect = Exception("User already registered")
    mocker.patch("app.routers.auth.anon_client", return_value=fake_anon)

    response = client.post(
        "/auth/register",
        json={"email": "a@b.com", "password": "password123", "full_name": "A B"},
    )

    assert response.status_code == 400


def test_login_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="access-tok", refresh_token="refresh-tok"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/login", json={"email": "a@b.com", "password": "password123"})

    assert response.status_code == 200
    assert response.json() == {
        "token": "access-tok",
        "refreshToken": "refresh-tok",
        "user": {"id": "user-1", "email": "a@b.com"},
    }


def test_login_invalid_credentials_returns_401(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/login", json={"email": "a@b.com", "password": "wrong"})

    assert response.status_code == 401


def test_refresh_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.return_value = SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="a@b.com"),
        session=SimpleNamespace(access_token="new-access", refresh_token="new-refresh"),
    )
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/refresh", json={"refreshToken": "old-refresh"})

    assert response.status_code == 200
    assert response.json()["token"] == "new-access"


def test_refresh_invalid_token_returns_401(mocker):
    fake_client = mocker.MagicMock()
    fake_client.auth.refresh_session.side_effect = Exception("invalid refresh token")
    mocker.patch("app.routers.auth.anon_client", return_value=fake_client)

    response = client.post("/auth/refresh", json={"refreshToken": "bad"})

    assert response.status_code == 401


def test_logout_requires_auth():
    response = client.post("/auth/logout")
    assert response.status_code == 401


def test_logout_success_with_valid_token(mocker):
    mock_admin = mocker.patch("app.dependencies.admin_client")
    fake_user = SimpleNamespace(id="user-1", email="a@b.com")
    mock_admin.return_value.auth.get_user.return_value = SimpleNamespace(user=fake_user)

    response = client.post("/auth/logout", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 204
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_auth_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers'`

- [ ] **Step 3: Implement `app/routers/__init__.py`** (empty file) **and `app/routers/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas import RegisterRequest, LoginRequest, RefreshRequest, AuthResponse, UserOut
from app.supabase_client import anon_client, admin_client
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    client = anon_client()
    try:
        result = client.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {"data": {"full_name": payload.full_name}},
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    user = result.user
    if user is None:
        raise HTTPException(status_code=400, detail="Registration failed")

    try:
        admin_client().table("profiles").insert(
            {"id": user.id, "full_name": payload.full_name}
        ).execute()
    except Exception as exc:
        try:
            admin_client().auth.admin.delete_user(user.id)
        except Exception:
            pass
        raise HTTPException(
            status_code=500, detail="Registration failed while creating profile"
        ) from exc

    return {"id": user.id, "email": user.email}


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest):
    client = anon_client()
    try:
        result = client.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc

    session = result.session
    user = result.user
    if session is None or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return AuthResponse(
        token=session.access_token,
        refreshToken=session.refresh_token,
        user=UserOut(id=user.id, email=user.email),
    )


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest):
    client = anon_client()
    try:
        result = client.auth.refresh_session(payload.refreshToken)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc

    session = result.session
    user = result.user
    if session is None or user is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return AuthResponse(
        token=session.access_token,
        refreshToken=session.refresh_token,
        user=UserOut(id=user.id, email=user.email),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: dict = Depends(get_current_user)):
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_auth_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/__init__.py app/routers/auth.py tests/test_auth_router.py
git commit -m "feat: add auth router (register, login, refresh, logout)"
```

---

### Task 6: OTP code generator

**Files:**
- Create: `srwiki-be/app/otp.py`
- Test: `srwiki-be/tests/test_otp.py`

**Interfaces:**
- Produces: `app.otp.generate_code() -> str` (6-digit numeric string, used by Task 8's send-otp endpoint)

- [ ] **Step 1: Write the failing test**

```python
# srwiki-be/tests/test_otp.py
import re
from app.otp import generate_code


def test_generate_code_is_six_digits():
    codes = [generate_code() for _ in range(200)]
    assert all(re.fullmatch(r"\d{6}", code) for code in codes)
    assert len(set(codes)) > 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_otp.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.otp'`

- [ ] **Step 3: Implement `app/otp.py`**

```python
import secrets


def generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_otp.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/otp.py tests/test_otp.py
git commit -m "feat: add 6-digit OTP code generator"
```

---

### Task 7: Profile router — GET / PUT `/profile`

**Files:**
- Create: `srwiki-be/app/routers/profile.py`
- Test: `srwiki-be/tests/test_profile_router.py`

**Interfaces:**
- Consumes: `app.schemas.{ProfileOut, ProfileUpdateRequest}` (Task 3), `app.supabase_client.user_client` (Task 2), `app.dependencies.get_current_user` (Task 4)
- Produces: `app.routers.profile.router` (prefix `/profile`) with `GET /profile`, `PUT /profile`; module-level helper `_fetch_profile_row(client, user_id: str) -> dict` reused by Task 8/9.

- [ ] **Step 1: Write the failing tests**

```python
# srwiki-be/tests/test_profile_router.py
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import profile
from app.dependencies import get_current_user

app = FastAPI()
app.include_router(profile.router)


def override_current_user():
    return {"id": "user-1", "email": "a@b.com", "access_token": "tok"}


app.dependency_overrides[get_current_user] = override_current_user
client = TestClient(app)

PROFILE_ROW = {
    "id": "user-1",
    "full_name": "A B",
    "phone": None,
    "phone_verified": False,
    "address": None,
    "date_of_birth": None,
    "created_at": "2026-08-05T00:00:00Z",
    "updated_at": "2026-08-05T00:00:00Z",
}


def test_get_profile_success(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=PROFILE_ROW
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.get("/profile")

    assert response.status_code == 200
    assert response.json()["email"] == "a@b.com"
    assert response.json()["full_name"] == "A B"


def test_get_profile_not_found(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data=None
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.get("/profile")

    assert response.status_code == 404


def test_update_profile_sends_only_provided_fields(mocker):
    fake_client = mocker.MagicMock()
    fake_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "full_name": "New Name"}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_client)

    response = client.put("/profile", json={"full_name": "New Name"})

    assert response.status_code == 200
    update_call = fake_client.table.return_value.update.call_args[0][0]
    assert update_call["full_name"] == "New Name"
    assert "address" not in update_call
    assert "phone" not in update_call


def test_update_profile_rejects_phone_field():
    response = client.put("/profile", json={"phone": "+84912345678"})
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_profile_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.profile'`

- [ ] **Step 3: Implement `app/routers/profile.py`**

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import get_current_user
from app.schemas import ProfileOut, ProfileUpdateRequest
from app.supabase_client import user_client

router = APIRouter(prefix="/profile", tags=["profile"])


def _fetch_profile_row(client, user_id: str) -> dict:
    result = client.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result.data


@router.get("", response_model=ProfileOut)
def get_profile(current_user: dict = Depends(get_current_user)):
    client = user_client(current_user["access_token"])
    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)


@router.put("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    client = user_client(current_user["access_token"])
    updates = payload.model_dump(exclude_unset=True)
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    client.table("profiles").update(updates).eq("id", current_user["id"]).execute()
    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_profile_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/profile.py tests/test_profile_router.py
git commit -m "feat: add GET/PUT /profile with RLS-respecting user client"
```

---

### Task 8: Profile router — phone OTP endpoints

**Files:**
- Modify: `srwiki-be/app/routers/profile.py`
- Modify: `srwiki-be/tests/test_profile_router.py`

**Interfaces:**
- Consumes: `app.otp.generate_code` (Task 6), `app.phone.{validate_phone_e164, InvalidPhoneNumberError}` (Task 3), `app.schemas.{SendOtpRequest, VerifyOtpRequest}` (Task 3), `app.supabase_client.admin_client` (Task 2), `app.config.get_settings` (Task 1), `_fetch_profile_row` (Task 7)
- Produces: `POST /profile/phone/send-otp`, `POST /profile/phone/verify-otp` on the same `router`. OTP rows live in the `otp_codes` table (schema defined in Task 11); this task writes to it via `admin_client()` only.

- [ ] **Step 1: Append the failing tests**

Add to `srwiki-be/tests/test_profile_router.py`:

```python
def test_send_otp_invalid_phone_returns_422():
    response = client.post("/profile/phone/send-otp", json={"phone": "not-a-phone"})
    assert response.status_code == 422


def test_send_otp_success_returns_debug_code_in_debug_mode(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)
    fake_settings = mocker.MagicMock(otp_debug_mode=True)
    mocker.patch("app.routers.profile.get_settings", return_value=fake_settings)

    response = client.post("/profile/phone/send-otp", json={"phone": "+84912345678"})

    assert response.status_code == 200
    assert "debug_otp" in response.json()
    fake_admin.table.return_value.insert.assert_called_once()


def test_send_otp_omits_debug_code_when_debug_mode_off(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)
    fake_settings = mocker.MagicMock(otp_debug_mode=False)
    mocker.patch("app.routers.profile.get_settings", return_value=fake_settings)

    response = client.post("/profile/phone/send-otp", json={"phone": "+84912345678"})

    assert response.status_code == 200
    assert "debug_otp" not in response.json()


def test_verify_otp_success(mocker):
    fake_admin = mocker.MagicMock()
    query = fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[{"id": "otp-1"}])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    fake_user_client = mocker.MagicMock()
    fake_user_client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = SimpleNamespace(
        data={**PROFILE_ROW, "phone": "+84912345678", "phone_verified": True}
    )
    mocker.patch("app.routers.profile.user_client", return_value=fake_user_client)

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "123456"}
    )

    assert response.status_code == 200
    assert response.json()["phone_verified"] is True


def test_verify_otp_invalid_code_returns_400(mocker):
    fake_admin = mocker.MagicMock()
    query = fake_admin.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value
    query.execute.return_value = SimpleNamespace(data=[])
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    response = client.post(
        "/profile/phone/verify-otp", json={"phone": "+84912345678", "code": "000000"}
    )

    assert response.status_code == 400
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `pytest tests/test_profile_router.py -v -k otp`
Expected: FAIL with `404 Not Found` (routes don't exist yet)

- [ ] **Step 3: Append to `app/routers/profile.py`**

Add these imports at the top (alongside the existing ones from Task 7):

```python
from datetime import timedelta
from app.config import get_settings
from app.otp import generate_code
from app.phone import validate_phone_e164, InvalidPhoneNumberError
from app.schemas import SendOtpRequest, VerifyOtpRequest
from app.supabase_client import admin_client
```

Append to the bottom of the file:

```python
OTP_TTL_MINUTES = 5


@router.post("/phone/send-otp")
def send_otp(payload: SendOtpRequest, current_user: dict = Depends(get_current_user)):
    try:
        phone = validate_phone_e164(payload.phone)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    client = admin_client()
    client.table("otp_codes").update({"consumed": True}).eq(
        "user_id", current_user["id"]
    ).eq("consumed", False).execute()

    code = generate_code()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=OTP_TTL_MINUTES)).isoformat()
    client.table("otp_codes").insert(
        {
            "user_id": current_user["id"],
            "phone": phone,
            "code": code,
            "expires_at": expires_at,
        }
    ).execute()

    response = {"message": "OTP sent"}
    if get_settings().otp_debug_mode:
        print(f"[OTP DEBUG] phone={phone} code={code}")
        response["debug_otp"] = code
    return response


@router.post("/phone/verify-otp", response_model=ProfileOut)
def verify_otp(payload: VerifyOtpRequest, current_user: dict = Depends(get_current_user)):
    try:
        phone = validate_phone_e164(payload.phone)
    except InvalidPhoneNumberError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    admin = admin_client()
    now = datetime.now(timezone.utc).isoformat()
    result = (
        admin.table("otp_codes")
        .select("*")
        .eq("user_id", current_user["id"])
        .eq("phone", phone)
        .eq("code", payload.code)
        .eq("consumed", False)
        .gte("expires_at", now)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    otp_row = result.data[0]
    admin.table("otp_codes").update({"consumed": True}).eq("id", otp_row["id"]).execute()

    client = user_client(current_user["access_token"])
    client.table("profiles").update(
        {"phone": phone, "phone_verified": True, "updated_at": now}
    ).eq("id", current_user["id"]).execute()

    row = _fetch_profile_row(client, current_user["id"])
    return ProfileOut(email=current_user["email"], **row)
```

- [ ] **Step 4: Run to verify all profile tests pass**

Run: `pytest tests/test_profile_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/routers/profile.py tests/test_profile_router.py
git commit -m "feat: add phone OTP send/verify endpoints"
```

---

### Task 9: Profile router — DELETE `/profile`

**Files:**
- Modify: `srwiki-be/app/routers/profile.py`
- Modify: `srwiki-be/tests/test_profile_router.py`

**Interfaces:**
- Consumes: `app.supabase_client.admin_client` (Task 2)
- Produces: `DELETE /profile` on the same `router`

- [ ] **Step 1: Append the failing test**

```python
def test_delete_profile_calls_admin_delete_user(mocker):
    fake_admin = mocker.MagicMock()
    mocker.patch("app.routers.profile.admin_client", return_value=fake_admin)

    response = client.delete("/profile")

    assert response.status_code == 204
    fake_admin.auth.admin.delete_user.assert_called_once_with("user-1")
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_profile_router.py -v -k delete_profile`
Expected: FAIL with `405 Method Not Allowed`

- [ ] **Step 3: Append to `app/routers/profile.py`**

```python
from fastapi import status


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(current_user: dict = Depends(get_current_user)):
    admin_client().auth.admin.delete_user(current_user["id"])
    return None
```

(Add `from fastapi import status` to the existing `fastapi` import line at the top instead of a second import line if one already exists.)

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/test_profile_router.py -v`
Expected: PASS (all profile router tests)

- [ ] **Step 5: Commit**

```bash
git add app/routers/profile.py tests/test_profile_router.py
git commit -m "feat: add DELETE /profile (admin account deletion)"
```

---

### Task 10: Wire routers into the app

**Files:**
- Modify: `srwiki-be/app/main.py`
- Create: `srwiki-be/tests/test_main.py`

**Interfaces:**
- Consumes: `app.routers.auth.router` (Task 5), `app.routers.profile.router` (Task 9)
- Produces: fully-wired `app.main.app` — every route from Tasks 5-9 reachable through the real app

- [ ] **Step 1: Write the failing test**

```python
# srwiki-be/tests/test_main.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_all_expected_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert {
        "/health",
        "/auth/register",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/profile",
        "/profile/phone/send-otp",
        "/profile/phone/verify-otp",
    } <= paths


def test_cors_headers_present_for_allowed_origin():
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_main.py -v`
Expected: FAIL — `/auth/register` etc. missing from `paths`

- [ ] **Step 3: Modify `app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.routers import auth, profile


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SR-WIKI API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(profile.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Run the full backend test suite**

Run: `pytest -v`
Expected: PASS — every test file from Tasks 1-10 green

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_main.py
git commit -m "feat: wire auth and profile routers into the app"
```

---

### Task 11: Supabase SQL migrations

**Files:**
- Create: `srwiki-be/supabase/migrations/0001_profiles.sql`, `srwiki-be/supabase/migrations/0002_otp_codes.sql`

**Interfaces:**
- Produces: the `profiles` and `otp_codes` tables the rest of the backend assumes exist (matches the column names used in Tasks 7-9). Applied manually in Task 12 — there's no automated test for SQL files in this plan.

- [ ] **Step 1: Write `supabase/migrations/0001_profiles.sql`**

```sql
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  phone text,
  phone_verified boolean not null default false,
  address text,
  date_of_birth date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "Users can view their own profile"
  on public.profiles for select
  to authenticated
  using (auth.uid() = id);

create policy "Users can update their own profile"
  on public.profiles for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

create policy "Users can insert their own profile"
  on public.profiles for insert
  to authenticated
  with check (auth.uid() = id);
```

- [ ] **Step 2: Write `supabase/migrations/0002_otp_codes.sql`**

```sql
create table public.otp_codes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  phone text not null,
  code text not null,
  expires_at timestamptz not null,
  consumed boolean not null default false,
  created_at timestamptz not null default now()
);

create index otp_codes_user_id_idx on public.otp_codes (user_id);

alter table public.otp_codes enable row level security;
-- No policies are created: RLS with zero policies denies all access to the
-- anon/authenticated roles. Only the service-role key (used exclusively by
-- the backend's admin_client) bypasses RLS, which is the only intended
-- access path for this table.
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations
git commit -m "feat: add profiles and otp_codes table migrations with RLS"
```

---

### Task 12: Create the Supabase project and apply migrations (manual)

**Files:** none (dashboard actions + filling in `srwiki-be/.env`, which is gitignored)

This task has no automated test — it's the point where the user provisions real
infrastructure. Everything from Task 13 onward, and the final E2E QA task, depends
on it being done.

- [ ] **Step 1:** Go to https://supabase.com/dashboard and sign in (or create an account).
- [ ] **Step 2:** Click "New Project" → choose an organization → name it `srwiki` → set and save a database password → pick a region close to you → click "Create new project". Wait ~2 minutes for provisioning.
- [ ] **Step 3:** In the project, go to Project Settings → API. Copy the "Project URL", the `anon` `public` key, and the `service_role` key.
- [ ] **Step 4:** In `srwiki-be/`, copy the template and fill it in:

```bash
cd /home/khoapa/PycharmProjects/WelcomeScreen/SR-WIKI/srwiki-be
cp .env.template .env
```

Edit `.env` and paste the three values into `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.

- [ ] **Step 5:** Go to Authentication → Providers → Email, and toggle **off** "Confirm email". This makes `sign_up` return an active session immediately, which this project's register flow relies on for local dev (see Task 5). Re-enable it later for production if desired.
- [ ] **Step 6:** Go to SQL Editor → New query. Paste the full contents of `supabase/migrations/0001_profiles.sql`, click Run. Repeat with `0002_otp_codes.sql`.
- [ ] **Step 7:** Verify in Table Editor that `profiles` and `otp_codes` both appear with the RLS shield icon enabled.

---

### Task 13: Backend Dockerfile + Procfile

**Files:**
- Create: `srwiki-be/Dockerfile`, `srwiki-be/Procfile`

**Interfaces:**
- Consumes: `requirements.txt` (Task 1), `app/` package (Tasks 1-10)
- Produces: a container image runnable locally and deployable to Render/Railway (Procfile covers the latter's buildpack path)

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 2: Write `Procfile`**

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 3: Verify the image builds (skip if Docker isn't installed locally — it will still work on Render/Railway's build step)**

Run: `docker build -t srwiki-be:local .` (from `srwiki-be/`)
Expected: build completes with no errors

- [ ] **Step 4: Commit**

```bash
git add Dockerfile Procfile
git commit -m "chore: add backend Dockerfile and Procfile"
```

---

## Phase B — Frontend (`srwiki-fe/`)

Frontend automated testing is out of scope for this pass (see Global Constraints).
Every task's verification is `npm run build` (type-check + bundle) and `npm run
lint`, plus a manual `npm run dev` check where noted.

### Task 14: Vite scaffold, path alias, base dependencies

**Files:**
- Create: `srwiki-fe/` (via Vite scaffold — `package.json`, `vite.config.ts`, `tsconfig*.json`, `src/main.tsx`, `src/App.tsx`, `index.html`, etc.)
- Modify: `srwiki-fe/vite.config.ts`, `srwiki-fe/tsconfig.app.json` (or `tsconfig.json` if the installed Vite version doesn't split configs)

**Interfaces:**
- Produces: a buildable Vite+React+TS project with the `~root/*` → `src/*` alias resolvable both by the bundler (`vite.config.ts`) and by TypeScript (`tsconfig`), and with `react-router-dom`, `@tanstack/react-query`, `axios`, `jotai`, `react-toastify`, `react-phone-number-input` installed.

- [ ] **Step 1: Scaffold the project**

```bash
cd /home/khoapa/PycharmProjects/WelcomeScreen/SR-WIKI
npm create vite@latest srwiki-fe -- --template react-ts
cd srwiki-fe
npm install
```

- [ ] **Step 2: Install the app dependencies**

```bash
npm install react-router-dom @tanstack/react-query axios jotai react-toastify react-phone-number-input
```

- [ ] **Step 3: Add the `~root` alias to `vite.config.ts`**

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '~root': path.resolve(__dirname, './src'),
    },
  },
});
```

- [ ] **Step 4: Add the matching path to TypeScript config**

Open `tsconfig.app.json` (Vite 5+ splits config into `tsconfig.json` / `tsconfig.app.json` / `tsconfig.node.json`; if your scaffolded version only has a single `tsconfig.json`, edit that one instead) and add inside `compilerOptions`:

```json
"baseUrl": ".",
"paths": {
  "~root/*": ["./src/*"]
}
```

- [ ] **Step 5: Verify the build succeeds**

Run: `npm run build`
Expected: build completes with no errors

- [ ] **Step 6: Commit**

```bash
git add srwiki-fe
git commit -m "chore: scaffold Vite React+TS frontend with ~root alias"
```

---

### Task 15: Tailwind CSS setup

**Files:**
- Create: `srwiki-fe/tailwind.config.js`, `srwiki-fe/postcss.config.js`
- Modify: `srwiki-fe/src/index.css`, `srwiki-fe/src/App.tsx`

**Interfaces:**
- Produces: Tailwind utility classes usable in every component from here on

- [ ] **Step 1: Install Tailwind and generate config**

```bash
cd srwiki-fe
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

- [ ] **Step 2: Configure `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 3: Replace `src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Add a temporary marker class to `src/App.tsx` to prove the pipeline works**

Wrap the existing scaffolded content's outer element with `className="p-4"` (any real Tailwind utility class works — this is just the verification marker; it will be replaced entirely in Task 21).

- [ ] **Step 5: Verify Tailwind actually processed the class**

Run: `npm run build && grep -q '\.p-4' dist/assets/*.css && echo "TAILWIND OK"`
Expected: prints `TAILWIND OK`

- [ ] **Step 6: Commit**

```bash
git add tailwind.config.js postcss.config.js src/index.css src/App.tsx
git commit -m "chore: add Tailwind CSS"
```

---

### Task 16: ESLint + Prettier

**Files:**
- Modify: `srwiki-fe/eslint.config.js` (Vite's react-ts template ships one with typescript-eslint + react-hooks + react-refresh already configured)
- Create: `srwiki-fe/.prettierrc`
- Modify: `srwiki-fe/package.json` (add `lint` / `format` scripts if the template didn't already add `lint`)

**Interfaces:**
- Produces: `npm run lint` and `npm run format` — the quality gate every later FE task must pass

- [ ] **Step 1: Install Prettier and the ESLint/Prettier bridge**

```bash
cd srwiki-fe
npm install -D prettier eslint-config-prettier
```

- [ ] **Step 2: Write `.prettierrc`**

```json
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100
}
```

- [ ] **Step 3: Append `eslint-config-prettier` as the last entry in `eslint.config.js`'s exported config array**

At the end of the array passed to `export default [...]` (or `defineConfig([...])`, depending on template version), add:

```js
import prettier from 'eslint-config-prettier';
// ...
prettier,
```

This must be the *last* item so its rule disables win over the earlier configs.

- [ ] **Step 4: Ensure `package.json` has both scripts**

```json
"scripts": {
  "lint": "eslint .",
  "format": "prettier --write ."
}
```

- [ ] **Step 5: Verify**

Run: `npm run format && npm run lint`
Expected: `lint` exits 0 with no errors

- [ ] **Step 6: Commit**

```bash
git add eslint.config.js .prettierrc package.json package-lock.json
git commit -m "chore: add Prettier and wire it into ESLint"
```

---

### Task 17: Constants, utils, env template

**Files:**
- Create: `srwiki-fe/src/constants/index.ts`, `srwiki-fe/src/utils/index.ts`, `srwiki-fe/.env.template`
- Modify: `srwiki-fe/src/vite-env.d.ts`, `srwiki-fe/.gitignore`

**Interfaces:**
- Produces: `API_URL: string`, `Endpoints` (object with `AUTH_REGISTER`, `AUTH_LOGIN`, `AUTH_REFRESH`, `AUTH_LOGOUT`, `PROFILE`, `PROFILE_PHONE_SEND_OTP`, `PROFILE_PHONE_VERIFY_OTP` string paths), `isJsonString(value: string) -> boolean` — consumed by every task from here on.

- [ ] **Step 1: Write `src/constants/index.ts`**

```ts
export const API_URL = import.meta.env.VITE_API_BASE_URL as string;

export const Endpoints = {
  AUTH_REGISTER: '/auth/register',
  AUTH_LOGIN: '/auth/login',
  AUTH_REFRESH: '/auth/refresh',
  AUTH_LOGOUT: '/auth/logout',
  PROFILE: '/profile',
  PROFILE_PHONE_SEND_OTP: '/profile/phone/send-otp',
  PROFILE_PHONE_VERIFY_OTP: '/profile/phone/verify-otp',
} as const;
```

- [ ] **Step 2: Write `src/utils/index.ts`**

```ts
export const isJsonString = (value: string): boolean => {
  try {
    JSON.parse(value);
    return true;
  } catch {
    return false;
  }
};
```

- [ ] **Step 3: Extend `src/vite-env.d.ts` with the env var type**

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

- [ ] **Step 4: Write `.env.template`**

```
VITE_API_BASE_URL=http://localhost:8000
```

- [ ] **Step 5: Confirm `.gitignore` ignores `.env` but not `.env.template`**

Open `srwiki-fe/.gitignore` (Vite's scaffold already includes one). It should contain a bare `.env` line (or `.env.local` variants) but must NOT contain a wildcard `.env*` pattern, since that would also match and hide `.env.template` from git. If it only has specific lines like `.env`, `.env.local`, `.env.*.local`, it's already correct — leave it as is.

- [ ] **Step 6: Verify**

Run: `npm run build`
Expected: build succeeds (confirms `ImportMetaEnv` typing is valid)

- [ ] **Step 7: Commit**

```bash
git add src/constants src/utils src/vite-env.d.ts .env.template
git commit -m "feat: add API constants, isJsonString util, and env template"
```

---

### Task 18: Jotai store + authAtom

**Files:**
- Create: `srwiki-fe/src/stores/index.ts`, `srwiki-fe/src/screens/auth/login/stores.ts`

**Interfaces:**
- Consumes: `isJsonString` (Task 17)
- Produces: `localStore` (a Jotai `Store` instance), `authAtom` (a Jotai `atom<AuthState>`), `AuthState = { token: string; user: AuthUser } | null`, `AuthUser = { id: string; email: string }` — consumed by the HTTP client (Task 19), `ProtectedRoute` (Task 20), and every auth-aware component after that.

- [ ] **Step 1: Write `src/stores/index.ts`**

```ts
import { createStore } from 'jotai';

export const localStore = createStore();
```

- [ ] **Step 2: Write `src/screens/auth/login/stores.ts`**

```ts
import { atom } from 'jotai';
import { isJsonString } from '~root/utils';

export type AuthUser = {
  id: string;
  email: string;
};

export type AuthState = {
  token: string;
  user: AuthUser;
} | null;

const readInitialAuth = (): AuthState => {
  const raw = localStorage.getItem('auth');
  if (raw && isJsonString(raw)) {
    return JSON.parse(raw) as AuthState;
  }
  return null;
};

export const authAtom = atom<AuthState>(readInitialAuth());
```

- [ ] **Step 3: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed

- [ ] **Step 4: Commit**

```bash
git add src/stores src/screens
git commit -m "feat: add Jotai store and authAtom"
```

---

### Task 19: HTTP client with axios interceptors

**Files:**
- Create: `srwiki-fe/src/lib/http-client.ts`

**Interfaces:**
- Consumes: `API_URL`, `Endpoints` (Task 17), `isJsonString` (Task 17), `localStore` (Task 18), `authAtom` (Task 18)
- Produces: `httpClient` (configured axios instance) — every API hook from Task 21 onward imports this.

- [ ] **Step 1: Write `src/lib/http-client.ts`**

```ts
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { toast } from 'react-toastify';
import { API_URL, Endpoints } from '~root/constants';
import { isJsonString } from '~root/utils';
import { localStore } from '~root/stores';
import { authAtom } from '~root/screens/auth/login/stores';

export const httpClient = axios.create({
  baseURL: API_URL,
  timeout: 29000,
});

httpClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const auth = localStorage.getItem('auth');
    const token = auth && isJsonString(auth) ? JSON.parse(auth)?.token : null;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

let isRedirecting = false;
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token as string);
    }
  });
  failedQueue = [];
};

const redirectToLogin = () => {
  if (!isRedirecting) {
    isRedirecting = true;
    toast.error('Phiên đăng nhập đã hết hạn! Vui lòng đăng nhập lại.', {
      position: 'bottom-center',
      toastId: 'UNAUTHORIZED_ERROR',
    });
    setTimeout(() => {
      localStorage.removeItem('auth');
      localStorage.removeItem('refreshToken');
      localStore.set(authAtom, null);
      const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      window.location.href = `/auth/login${currentUrl ? `?callbackUrl=${encodeURIComponent(currentUrl)}` : ''}`;
    }, 1000);
    setTimeout(() => {
      isRedirecting = false;
    }, 5000);
  }
};

httpClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ errorCode?: string }>) => {
    const isAuthPage = window.location.pathname.startsWith('/auth/login');
    const isAccessRemovedPage = window.location.pathname.startsWith('/auth/access-removed');
    const status = error.response?.status;

    if (status === 401 && !isAuthPage) {
      const originalRequest = error.config!;
      const currentAuth = localStorage.getItem('auth');

      if (!currentAuth) {
        if (!isAccessRemovedPage) redirectToLogin();
        return Promise.reject(error);
      }

      if (originalRequest.url?.includes(Endpoints.AUTH_REFRESH)) {
        if (!isAccessRemovedPage) redirectToLogin();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers['Authorization'] = `Bearer ${token}`;
            return httpClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      isRefreshing = true;

      return new Promise((resolve, reject) => {
        const storedRefreshToken = localStorage.getItem('refreshToken');
        httpClient
          .post(Endpoints.AUTH_REFRESH, {
            ...(storedRefreshToken && { refreshToken: storedRefreshToken }),
          })
          .then(({ data }) => {
            const newToken = data.token;
            const auth = localStorage.getItem('auth');
            if (!auth) {
              processQueue(new Error('User logged out'), null);
              reject(new Error('User logged out'));
              return;
            }
            if (isJsonString(auth)) {
              const authData = JSON.parse(auth);
              authData.token = newToken;
              localStorage.setItem('auth', JSON.stringify(authData));
              localStore.set(authAtom, authData);
            }
            if (data.refreshToken) {
              localStorage.setItem('refreshToken', data.refreshToken);
            }
            originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
            processQueue(null, newToken);
            resolve(httpClient(originalRequest));
          })
          .catch((refreshError) => {
            processQueue(refreshError, null);
            if (!isAccessRemovedPage) redirectToLogin();
            reject(refreshError);
          })
          .finally(() => {
            isRefreshing = false;
          });
      });
    }

    if (status === 403 && !isAuthPage && !isAccessRemovedPage) {
      const errorCode = error.response?.data?.errorCode;
      if (errorCode === 'NOT_AUTHORIZED_TO_USE_APPLICATION') {
        if (!isRedirecting) {
          isRedirecting = true;
          localStorage.setItem('accessRemoved', 'true');
          setTimeout(() => {
            window.location.href = '/auth/access-removed';
          }, 100);
          setTimeout(() => {
            isRedirecting = false;
          }, 5000);
        }
        return Promise.reject(error);
      }
      toast.error('Bạn không có quyền truy cập tài nguyên này!', {
        position: 'bottom-center',
        toastId: 'FORBIDDEN_ERROR',
      });
    }

    return Promise.reject(error);
  },
);
```

Note: `NOT_AUTHORIZED_TO_USE_APPLICATION` is unreachable today — no backend endpoint in this project emits it. It's kept because the user asked to preserve the company's existing frontend convention for when a permissions feature is added later.

- [ ] **Step 2: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed

- [ ] **Step 3: Commit**

```bash
git add src/lib
git commit -m "feat: add axios http client with refresh-token interceptor"
```

---

### Task 20: App shell — providers, routing, ProtectedRoute

**Files:**
- Modify: `srwiki-fe/src/main.tsx`, `srwiki-fe/src/App.tsx`
- Create: `srwiki-fe/src/components/ProtectedRoute.tsx`
- Create: `srwiki-fe/src/screens/auth/login/LoginPage.tsx`, `srwiki-fe/src/screens/auth/register/RegisterPage.tsx`, `srwiki-fe/src/screens/auth/access-removed/AccessRemovedPage.tsx`, `srwiki-fe/src/screens/dashboard/DashboardPage.tsx`, `srwiki-fe/src/screens/profile/ProfilePage.tsx` (minimal stubs — filled in by Tasks 22-27)

**Interfaces:**
- Consumes: `localStore` (Task 18), `authAtom` (Task 18), `httpClient` (Task 19, imported transitively once hooks exist)
- Produces: working client-side routing with `/auth/login`, `/auth/register`, `/auth/access-removed` public, `/dashboard` and `/profile` behind `ProtectedRoute`

- [ ] **Step 1: Write `src/components/ProtectedRoute.tsx`**

```tsx
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAtomValue } from 'jotai';
import { authAtom } from '~root/screens/auth/login/stores';

export const ProtectedRoute = () => {
  const auth = useAtomValue(authAtom);
  const location = useLocation();

  if (!auth?.token) {
    const callbackUrl = `${location.pathname}${location.search}`;
    return <Navigate to={`/auth/login?callbackUrl=${encodeURIComponent(callbackUrl)}`} replace />;
  }

  return <Outlet />;
};
```

- [ ] **Step 2: Write the screen stubs**

`src/screens/auth/login/LoginPage.tsx`:
```tsx
export const LoginPage = () => <div>Login page</div>;
```

`src/screens/auth/register/RegisterPage.tsx`:
```tsx
export const RegisterPage = () => <div>Register page</div>;
```

`src/screens/dashboard/DashboardPage.tsx`:
```tsx
export const DashboardPage = () => <div>Dashboard page</div>;
```

`src/screens/profile/ProfilePage.tsx`:
```tsx
export const ProfilePage = () => <div>Profile page</div>;
```

`src/screens/auth/access-removed/AccessRemovedPage.tsx` (final content — simple enough not to need a later task):
```tsx
export const AccessRemovedPage = () => (
  <div className="flex min-h-screen items-center justify-center bg-slate-100">
    <div className="text-center">
      <h1 className="mb-2 text-xl font-semibold text-slate-900">Không có quyền truy cập</h1>
      <p className="text-slate-600">Tài khoản của bạn hiện không có quyền sử dụng ứng dụng này.</p>
    </div>
  </div>
);
```

- [ ] **Step 3: Write `src/App.tsx`**

```tsx
import { Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from '~root/components/ProtectedRoute';
import { LoginPage } from '~root/screens/auth/login/LoginPage';
import { RegisterPage } from '~root/screens/auth/register/RegisterPage';
import { AccessRemovedPage } from '~root/screens/auth/access-removed/AccessRemovedPage';
import { DashboardPage } from '~root/screens/dashboard/DashboardPage';
import { ProfilePage } from '~root/screens/profile/ProfilePage';

function App() {
  return (
    <Routes>
      <Route path="/auth/login" element={<LoginPage />} />
      <Route path="/auth/register" element={<RegisterPage />} />
      <Route path="/auth/access-removed" element={<AccessRemovedPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/auth/login" replace />} />
    </Routes>
  );
}

export default App;
```

- [ ] **Step 4: Write `src/main.tsx`**

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider as JotaiProvider } from 'jotai';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import App from './App';
import { localStore } from '~root/stores';
import './index.css';

const queryClient = new QueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <JotaiProvider store={localStore}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
          <ToastContainer />
        </BrowserRouter>
      </QueryClientProvider>
    </JotaiProvider>
  </StrictMode>,
);
```

- [ ] **Step 5: Verify build, then manually confirm redirect behavior**

Run: `npm run build && npm run lint`
Expected: both succeed

Then run: `npm run dev`, open `http://localhost:5173/dashboard` in a browser.
Expected: redirected to `/auth/login?callbackUrl=%2Fdashboard`

- [ ] **Step 6: Commit**

```bash
git add src/main.tsx src/App.tsx src/components src/screens
git commit -m "feat: wire routing, providers, and ProtectedRoute"
```

---

### Task 21: Auth API hooks — useLogin, useRegister

**Files:**
- Create: `srwiki-fe/src/apis/useLogin.ts`, `srwiki-fe/src/apis/useRegister.ts`

**Interfaces:**
- Consumes: `httpClient` (Task 19), `Endpoints` (Task 17), `localStore`/`authAtom` (Task 18)
- Produces: `useLogin()` (React Query mutation; on success persists `{token, user}` to `localStorage['auth']`, `refreshToken` to `localStorage['refreshToken']`, and writes to `authAtom` via `localStore.set`), `useRegister()` (mutation, no side effects on success — caller navigates)

- [ ] **Step 1: Write `src/apis/useLogin.ts`**

```ts
import { useMutation } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';
import { localStore } from '~root/stores';
import { authAtom, AuthUser } from '~root/screens/auth/login/stores';

type LoginPayload = { email: string; password: string };
type LoginResponse = { token: string; refreshToken: string; user: AuthUser };

const login = async (payload: LoginPayload): Promise<LoginResponse> => {
  const res = await httpClient.post<LoginResponse>(Endpoints.AUTH_LOGIN, payload);
  return res.data;
};

export const useLogin = () => {
  return useMutation({
    mutationFn: login,
    onSuccess: (data) => {
      const authData = { token: data.token, user: data.user };
      localStorage.setItem('auth', JSON.stringify(authData));
      localStorage.setItem('refreshToken', data.refreshToken);
      localStore.set(authAtom, authData);
    },
  });
};
```

- [ ] **Step 2: Write `src/apis/useRegister.ts`**

```ts
import { useMutation } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';

type RegisterPayload = {
  email: string;
  password: string;
  full_name: string;
};

const register = async (payload: RegisterPayload): Promise<{ id: string; email: string }> => {
  const res = await httpClient.post(Endpoints.AUTH_REGISTER, payload);
  return res.data;
};

export const useRegister = () => useMutation({ mutationFn: register });
```

- [ ] **Step 3: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed

- [ ] **Step 4: Commit**

```bash
git add src/apis
git commit -m "feat: add useLogin and useRegister API hooks"
```

---

### Task 22: LoginPage

**Files:**
- Modify: `srwiki-fe/src/screens/auth/login/LoginPage.tsx`

**Interfaces:**
- Consumes: `useLogin` (Task 21)
- Produces: functional login form; on success navigates to `callbackUrl` query param or `/dashboard`

- [ ] **Step 1: Replace `LoginPage.tsx` with the full implementation**

```tsx
import { FormEvent, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import { useLogin } from '~root/apis/useLogin';

export const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { mutate, isPending } = useLogin();

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    mutate(
      { email, password },
      {
        onSuccess: () => {
          const callbackUrl = searchParams.get('callbackUrl');
          navigate(callbackUrl || '/dashboard', { replace: true });
        },
        onError: () => {
          toast.error('Email hoặc mật khẩu không đúng.', { position: 'bottom-center' });
        },
      },
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-6 text-2xl font-semibold text-slate-900">Đăng nhập</h1>
        <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2"
        />
        <label className="mb-1 block text-sm font-medium text-slate-700">Mật khẩu</label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-6 w-full rounded border border-slate-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={isPending}
          className="w-full rounded bg-slate-900 py-2 text-white disabled:opacity-50"
        >
          {isPending ? 'Đang đăng nhập...' : 'Đăng nhập'}
        </button>
        <p className="mt-4 text-center text-sm text-slate-600">
          Chưa có tài khoản?{' '}
          <Link to="/auth/register" className="font-medium text-slate-900 underline">
            Đăng ký
          </Link>
        </p>
      </form>
    </div>
  );
};
```

- [ ] **Step 2: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed. Then `npm run dev`, open `/auth/login`, confirm the form renders and required-field validation blocks empty submit.

- [ ] **Step 3: Commit**

```bash
git add src/screens/auth/login/LoginPage.tsx
git commit -m "feat: implement LoginPage"
```

---

### Task 23: RegisterPage

**Files:**
- Modify: `srwiki-fe/src/screens/auth/register/RegisterPage.tsx`

**Interfaces:**
- Consumes: `useRegister` (Task 21)
- Produces: functional register form; on success toasts and navigates to `/auth/login`

- [ ] **Step 1: Replace `RegisterPage.tsx` with the full implementation**

```tsx
import { FormEvent, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import { useRegister } from '~root/apis/useRegister';

export const RegisterPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const navigate = useNavigate();
  const { mutate, isPending } = useRegister();

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    mutate(
      { email, password, full_name: fullName },
      {
        onSuccess: () => {
          toast.success('Đăng ký thành công! Vui lòng đăng nhập.', { position: 'bottom-center' });
          navigate('/auth/login', { replace: true });
        },
        onError: () => {
          toast.error('Đăng ký thất bại. Email có thể đã được sử dụng.', {
            position: 'bottom-center',
          });
        },
      },
    );
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-6 text-2xl font-semibold text-slate-900">Đăng ký</h1>
        <label className="mb-1 block text-sm font-medium text-slate-700">Họ và tên</label>
        <input
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2"
        />
        <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2"
        />
        <label className="mb-1 block text-sm font-medium text-slate-700">Mật khẩu</label>
        <input
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mb-6 w-full rounded border border-slate-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={isPending}
          className="w-full rounded bg-slate-900 py-2 text-white disabled:opacity-50"
        >
          {isPending ? 'Đang đăng ký...' : 'Đăng ký'}
        </button>
        <p className="mt-4 text-center text-sm text-slate-600">
          Đã có tài khoản?{' '}
          <Link to="/auth/login" className="font-medium text-slate-900 underline">
            Đăng nhập
          </Link>
        </p>
      </form>
    </div>
  );
};
```

- [ ] **Step 2: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed. Then `npm run dev`, open `/auth/register`, confirm the form renders.

- [ ] **Step 3: Commit**

```bash
git add src/screens/auth/register/RegisterPage.tsx
git commit -m "feat: implement RegisterPage"
```

---

### Task 24: Sidebar (right-side nav) + DashboardPage

**Files:**
- Create: `srwiki-fe/src/components/Sidebar.tsx`
- Modify: `srwiki-fe/src/screens/dashboard/DashboardPage.tsx`

**Interfaces:**
- Consumes: `authAtom` (Task 18), `httpClient` (Task 19), `Endpoints.AUTH_LOGOUT` (Task 17)
- Produces: `Sidebar` component (reused by ProfilePage in Task 25); DashboardPage with the nav rendered on the right per the hard requirement from the spec

- [ ] **Step 1: Write `src/components/Sidebar.tsx`**

```tsx
import { NavLink } from 'react-router-dom';
import { useSetAtom } from 'jotai';
import { authAtom } from '~root/screens/auth/login/stores';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded px-4 py-2 text-sm font-medium ${
    isActive ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-200'
  }`;

export const Sidebar = () => {
  const setAuth = useSetAtom(authAtom);

  const handleLogout = () => {
    // Fire the logout call while the token is still in localStorage (the
    // request interceptor reads it synchronously), then clear local state
    // once it settles — clearing first would race the interceptor and send
    // the request with no Authorization header.
    httpClient
      .post(Endpoints.AUTH_LOGOUT)
      .catch(() => {})
      .finally(() => {
        localStorage.removeItem('auth');
        localStorage.removeItem('refreshToken');
        setAuth(null);
      });
  };

  return (
    <nav className="flex w-56 flex-shrink-0 flex-col gap-1 border-l border-slate-200 bg-white p-4">
      <NavLink to="/dashboard" className={linkClass}>
        Dashboard
      </NavLink>
      <NavLink to="/profile" className={linkClass}>
        Hồ sơ
      </NavLink>
      <button
        onClick={handleLogout}
        className="mt-4 rounded px-4 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50"
      >
        Đăng xuất
      </button>
    </nav>
  );
};
```

Clearing `authAtom` doesn't need an explicit navigate — `ProtectedRoute` (Task 20) re-renders on the next atom change and redirects to `/auth/login` automatically since both Dashboard and Profile live under it.

- [ ] **Step 2: Replace `DashboardPage.tsx`**

```tsx
import { Sidebar } from '~root/components/Sidebar';

export const DashboardPage = () => {
  return (
    <div className="flex min-h-screen bg-slate-50">
      <main className="flex-1 p-8">
        <h1 className="mb-4 text-2xl font-semibold text-slate-900">Dashboard</h1>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {['Tổng quan', 'Hoạt động', 'Thông báo'].map((title) => (
            <div key={title} className="rounded-lg bg-white p-6 shadow">
              <h2 className="mb-2 text-lg font-medium text-slate-900">{title}</h2>
              <p className="text-sm text-slate-500">Nội dung sẽ được cập nhật sau.</p>
            </div>
          ))}
        </div>
      </main>
      <Sidebar />
    </div>
  );
};
```

`<main>` (flex-1) precedes `<Sidebar>` in the flex row, so the nav renders on the right edge of the screen.

- [ ] **Step 3: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed. Then log in via the dev server and confirm the Dashboard shows the nav on the right with Dashboard/Hồ sơ/Đăng xuất links, and Đăng xuất redirects back to `/auth/login`.

- [ ] **Step 4: Commit**

```bash
git add src/components/Sidebar.tsx src/screens/dashboard/DashboardPage.tsx
git commit -m "feat: implement Dashboard with right-side nav"
```

---

### Task 25: Profile API hooks + basic info form

**Files:**
- Create: `srwiki-fe/src/apis/useGetProfile.ts`, `srwiki-fe/src/apis/useUpdateProfile.ts`
- Modify: `srwiki-fe/src/screens/profile/ProfilePage.tsx`

**Interfaces:**
- Consumes: `httpClient` (Task 19), `Endpoints` (Task 17), `Sidebar` (Task 24)
- Produces: `Profile` type (`id, email, full_name, phone, phone_verified, address, date_of_birth, created_at, updated_at`), `useGetProfile()` (returns `{profile, isLoading, refetch}`), `useUpdateProfile()` (mutation accepting `Partial<Pick<Profile, 'full_name'|'address'|'date_of_birth'>>`) — `Profile` type is reused by Tasks 26-27.

- [ ] **Step 1: Write `src/apis/useGetProfile.ts`**

```ts
import { useQuery } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';

export type Profile = {
  id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  phone_verified: boolean;
  address: string | null;
  date_of_birth: string | null;
  created_at: string;
  updated_at: string;
};

export const useGetProfile = () => {
  const getProfile = async ({ signal }: { signal?: AbortSignal }): Promise<Profile> => {
    const res = await httpClient.get<Profile>(Endpoints.PROFILE, { signal });
    return res.data;
  };

  const { data, isLoading, refetch } = useQuery<Profile>({
    queryKey: [Endpoints.PROFILE],
    queryFn: getProfile,
  });

  return { profile: data, isLoading, refetch };
};
```

- [ ] **Step 2: Write `src/apis/useUpdateProfile.ts`**

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';
import { Profile } from '~root/apis/useGetProfile';

type UpdatePayload = Partial<Pick<Profile, 'full_name' | 'address' | 'date_of_birth'>>;

export const useUpdateProfile = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: UpdatePayload) => {
      const res = await httpClient.put<Profile>(Endpoints.PROFILE, payload);
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData([Endpoints.PROFILE], data);
    },
  });
};
```

- [ ] **Step 3: Replace `ProfilePage.tsx` with the basic-info form**

```tsx
import { FormEvent, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { Sidebar } from '~root/components/Sidebar';
import { useGetProfile } from '~root/apis/useGetProfile';
import { useUpdateProfile } from '~root/apis/useUpdateProfile';

export const ProfilePage = () => {
  const { profile, isLoading } = useGetProfile();
  const { mutate: updateProfile, isPending } = useUpdateProfile();
  const [fullName, setFullName] = useState('');
  const [address, setAddress] = useState('');
  const [dateOfBirth, setDateOfBirth] = useState('');

  useEffect(() => {
    if (profile) {
      setFullName(profile.full_name ?? '');
      setAddress(profile.address ?? '');
      setDateOfBirth(profile.date_of_birth ?? '');
    }
  }, [profile]);

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    updateProfile(
      { full_name: fullName, address, date_of_birth: dateOfBirth || null },
      {
        onSuccess: () => toast.success('Đã lưu hồ sơ.', { position: 'bottom-center' }),
        onError: () => toast.error('Lưu hồ sơ thất bại.', { position: 'bottom-center' }),
      },
    );
  };

  if (isLoading) {
    return <div className="p-8">Đang tải...</div>;
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <main className="flex-1 p-8">
        <h1 className="mb-6 text-2xl font-semibold text-slate-900">Hồ sơ cá nhân</h1>
        <form onSubmit={handleSubmit} className="max-w-md space-y-4 rounded-lg bg-white p-6 shadow">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Họ và tên</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Địa chỉ</label>
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Ngày sinh</label>
            <input
              type="date"
              value={dateOfBirth}
              onChange={(e) => setDateOfBirth(e.target.value)}
              className="w-full rounded border border-slate-300 px-3 py-2"
            />
          </div>
          <button
            type="submit"
            disabled={isPending}
            className="rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50"
          >
            {isPending ? 'Đang lưu...' : 'Lưu'}
          </button>
        </form>
      </main>
      <Sidebar />
    </div>
  );
};
```

- [ ] **Step 4: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed. Then, with the backend running (Task 12 must be done — real Supabase project), log in, go to `/profile`, edit full name/address/date of birth, save, confirm the toast and that a page refresh shows the saved values.

- [ ] **Step 5: Commit**

```bash
git add src/apis/useGetProfile.ts src/apis/useUpdateProfile.ts src/screens/profile/ProfilePage.tsx
git commit -m "feat: add profile read/update hooks and basic info form"
```

---

### Task 26: PhoneInput + OTP hooks + OtpModal, wired into ProfilePage

**Files:**
- Create: `srwiki-fe/src/components/PhoneInput.tsx`, `srwiki-fe/src/components/OtpModal.tsx`, `srwiki-fe/src/apis/useSendOtp.ts`, `srwiki-fe/src/apis/useVerifyOtp.ts`
- Modify: `srwiki-fe/src/screens/profile/ProfilePage.tsx`

**Interfaces:**
- Consumes: `httpClient`/`Endpoints` (Tasks 17/19), `Profile` type (Task 25), `react-phone-number-input` (installed in Task 14)
- Produces: `PhoneInput` (default country `VN`, produces E.164 string), `useSendOtp()` (mutation, returns `{message, debug_otp?}`), `useVerifyOtp()` (mutation, returns updated `Profile` and syncs the `useGetProfile` query cache), `OtpModal` (props `{phone, onClose, onVerified}`)

- [ ] **Step 1: Write `src/components/PhoneInput.tsx`**

```tsx
import PhoneInputWithCountry from 'react-phone-number-input';
import 'react-phone-number-input/style.css';

type Props = {
  value: string;
  onChange: (value: string) => void;
};

export const PhoneInput = ({ value, onChange }: Props) => {
  return (
    <PhoneInputWithCountry
      international
      defaultCountry="VN"
      value={value}
      onChange={(val) => onChange(val ?? '')}
      className="phone-input rounded border border-slate-300 px-3 py-2"
    />
  );
};
```

- [ ] **Step 2: Write `src/apis/useSendOtp.ts`**

```ts
import { useMutation } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';

type SendOtpResponse = { message: string; debug_otp?: string };

export const useSendOtp = () =>
  useMutation({
    mutationFn: async (phone: string) => {
      const res = await httpClient.post<SendOtpResponse>(Endpoints.PROFILE_PHONE_SEND_OTP, {
        phone,
      });
      return res.data;
    },
  });
```

- [ ] **Step 3: Write `src/apis/useVerifyOtp.ts`**

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';
import { Profile } from '~root/apis/useGetProfile';

export const useVerifyOtp = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { phone: string; code: string }) => {
      const res = await httpClient.post<Profile>(Endpoints.PROFILE_PHONE_VERIFY_OTP, payload);
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData([Endpoints.PROFILE], data);
    },
  });
};
```

- [ ] **Step 4: Write `src/components/OtpModal.tsx`**

```tsx
import { FormEvent, useEffect, useState } from 'react';
import { toast } from 'react-toastify';
import { useSendOtp } from '~root/apis/useSendOtp';
import { useVerifyOtp } from '~root/apis/useVerifyOtp';

const OTP_TTL_SECONDS = 5 * 60;

type Props = {
  phone: string;
  onClose: () => void;
  onVerified: () => void;
};

export const OtpModal = ({ phone, onClose, onVerified }: Props) => {
  const [code, setCode] = useState('');
  const [secondsLeft, setSecondsLeft] = useState(OTP_TTL_SECONDS);
  const { mutate: sendOtp, isPending: isSending } = useSendOtp();
  const { mutate: verifyOtp, isPending: isVerifying } = useVerifyOtp();

  const requestOtp = () => {
    sendOtp(phone, {
      onSuccess: (data) => {
        if (data.debug_otp) {
          toast.info(`Mã OTP (dev mode): ${data.debug_otp}`, {
            position: 'bottom-center',
            autoClose: false,
          });
        }
      },
      onError: () => toast.error('Không gửi được mã OTP.', { position: 'bottom-center' }),
    });
  };

  useEffect(() => {
    requestOtp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const timer = setInterval(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearInterval(timer);
  }, [secondsLeft]);

  const handleResend = () => {
    setSecondsLeft(OTP_TTL_SECONDS);
    requestOtp();
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    verifyOtp(
      { phone, code },
      {
        onSuccess: () => {
          toast.success('Xác thực số điện thoại thành công.', { position: 'bottom-center' });
          onVerified();
        },
        onError: () =>
          toast.error('Mã OTP không đúng hoặc đã hết hạn.', { position: 'bottom-center' }),
      },
    );
  };

  const minutes = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
  const seconds = String(secondsLeft % 60).padStart(2, '0');

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-2 text-lg font-semibold text-slate-900">Xác thực số điện thoại</h2>
        <p className="mb-4 text-sm text-slate-600">Nhập mã 6 số đã gửi tới {phone}.</p>
        <form onSubmit={handleSubmit}>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={6}
            required
            className="mb-2 w-full rounded border border-slate-300 px-3 py-2 tracking-widest"
          />
          <p className="mb-4 text-xs text-slate-500">
            Mã hết hạn sau {minutes}:{seconds}
          </p>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={isVerifying}
              className="flex-1 rounded bg-slate-900 py-2 text-white disabled:opacity-50"
            >
              Xác nhận
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-slate-300 px-4 py-2 text-slate-700"
            >
              Đóng
            </button>
          </div>
          <button
            type="button"
            onClick={handleResend}
            disabled={isSending || secondsLeft > 0}
            className="mt-3 text-sm font-medium text-slate-700 underline disabled:opacity-40"
          >
            Gửi lại mã
          </button>
        </form>
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Wire the phone field into `ProfilePage.tsx`**

Add these imports to `src/screens/profile/ProfilePage.tsx`:

```tsx
import { useState } from 'react';
import { PhoneInput } from '~root/components/PhoneInput';
import { OtpModal } from '~root/components/OtpModal';
```

(merge the `useState`/`useEffect` import with the existing `FormEvent, useEffect, useState` line from Task 25). Add state:

```tsx
const [phone, setPhone] = useState('');
const [showOtpModal, setShowOtpModal] = useState(false);
```

In the `useEffect` that seeds form state from `profile`, add `setPhone(profile.phone ?? '');`. Insert this block into the form, between the "Địa chỉ" field and the submit button:

```tsx
<div>
  <label className="mb-1 block text-sm font-medium text-slate-700">Số điện thoại</label>
  <div className="flex items-center gap-2">
    <PhoneInput value={phone} onChange={setPhone} />
    {profile?.phone_verified && profile.phone === phone ? (
      <span className="rounded bg-green-100 px-2 py-1 text-xs font-medium text-green-700">
        Đã xác thực
      </span>
    ) : (
      <button
        type="button"
        onClick={() => setShowOtpModal(true)}
        disabled={!phone}
        className="rounded border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-40"
      >
        Xác thực
      </button>
    )}
  </div>
</div>
```

And after the closing `</form>`, before `</main>`:

```tsx
{showOtpModal && (
  <OtpModal
    phone={phone}
    onClose={() => setShowOtpModal(false)}
    onVerified={() => setShowOtpModal(false)}
  />
)}
```

- [ ] **Step 6: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed. Then with the real backend running (needs Task 12's Supabase project), on `/profile`: pick a country + enter a number, click Xác thực, confirm the modal shows a toast with `debug_otp`, enter that code, confirm "Đã xác thực" badge appears.

- [ ] **Step 7: Commit**

```bash
git add src/components/PhoneInput.tsx src/components/OtpModal.tsx src/apis/useSendOtp.ts src/apis/useVerifyOtp.ts src/screens/profile/ProfilePage.tsx
git commit -m "feat: add phone OTP verification to ProfilePage"
```

---

### Task 27: Delete account

**Files:**
- Create: `srwiki-fe/src/apis/useDeleteAccount.ts`
- Modify: `srwiki-fe/src/screens/profile/ProfilePage.tsx`

**Interfaces:**
- Consumes: `httpClient`/`Endpoints` (Tasks 17/19), `authAtom` (Task 18)
- Produces: `useDeleteAccount()` mutation; wired "Xoá tài khoản" button with a native confirm dialog that clears auth state and redirects to `/auth/login` on success

- [ ] **Step 1: Write `src/apis/useDeleteAccount.ts`**

```ts
import { useMutation } from '@tanstack/react-query';
import { httpClient } from '~root/lib/http-client';
import { Endpoints } from '~root/constants';

export const useDeleteAccount = () =>
  useMutation({
    mutationFn: async () => {
      await httpClient.delete(Endpoints.PROFILE);
    },
  });
```

- [ ] **Step 2: Wire it into `ProfilePage.tsx`**

Add imports:

```tsx
import { useNavigate } from 'react-router-dom';
import { useSetAtom } from 'jotai';
import { authAtom } from '~root/screens/auth/login/stores';
import { useDeleteAccount } from '~root/apis/useDeleteAccount';
```

Inside the component:

```tsx
const navigate = useNavigate();
const setAuth = useSetAtom(authAtom);
const { mutate: deleteAccount, isPending: isDeleting } = useDeleteAccount();

const handleDelete = () => {
  if (!window.confirm('Bạn chắc chắn muốn xoá tài khoản? Hành động này không thể hoàn tác.')) {
    return;
  }
  deleteAccount(undefined, {
    onSuccess: () => {
      localStorage.removeItem('auth');
      localStorage.removeItem('refreshToken');
      setAuth(null);
      navigate('/auth/login', { replace: true });
    },
    onError: () => toast.error('Xoá tài khoản thất bại.', { position: 'bottom-center' }),
  });
};
```

Add the button after the phone field block, before the submit button (or as a visually separated block after the form, e.g. right after the closing `</form>` and before the `OtpModal` block):

```tsx
<div className="mt-6 max-w-md rounded-lg border border-red-200 bg-red-50 p-4">
  <p className="mb-2 text-sm text-red-700">
    Xoá tài khoản sẽ xoá vĩnh viễn toàn bộ dữ liệu của bạn.
  </p>
  <button
    type="button"
    onClick={handleDelete}
    disabled={isDeleting}
    className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
  >
    {isDeleting ? 'Đang xoá...' : 'Xoá tài khoản'}
  </button>
</div>
```

- [ ] **Step 3: Verify**

Run: `npm run build && npm run lint`
Expected: both succeed. Manually: click Xoá tài khoản, confirm the browser confirm dialog, confirm redirect to `/auth/login` and that logging in again with the same credentials fails.

- [ ] **Step 4: Commit**

```bash
git add src/apis/useDeleteAccount.ts src/screens/profile/ProfilePage.tsx
git commit -m "feat: add delete account flow"
```

---

### Task 28: netlify.toml + frontend Dockerfile

**Files:**
- Create: `srwiki-fe/netlify.toml`, `srwiki-fe/Dockerfile`

**Interfaces:**
- Produces: Netlify build config (used by Task 30's deploy) and a containerized static-file server for local/dev use

- [ ] **Step 1: Write `netlify.toml`**

```toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
# build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# serve stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

- [ ] **Step 3: Verify the image builds (skip if Docker isn't installed locally)**

Run: `docker build -t srwiki-fe:local .` (from `srwiki-fe/`)
Expected: build completes with no errors

- [ ] **Step 4: Commit**

```bash
git add netlify.toml Dockerfile
git commit -m "chore: add netlify.toml and frontend Dockerfile"
```

---

### Task 29: Root docker-compose.yml

**Files:**
- Create: `docker-compose.yml` (repo root, alongside `srwiki-be/` and `srwiki-fe/`)

**Interfaces:**
- Consumes: `srwiki-be/Dockerfile` (Task 13), `srwiki-fe/Dockerfile` (Task 28), `srwiki-be/.env` (Task 12, gitignored — must exist locally for the backend service to start with real values)

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  backend:
    build: ./srwiki-be
    ports:
      - "8000:8000"
    env_file:
      - ./srwiki-be/.env
  frontend:
    build: ./srwiki-fe
    ports:
      - "8080:80"
    depends_on:
      - backend
```

- [ ] **Step 2: Verify the compose file is syntactically valid**

Run: `docker compose config`
Expected: prints the resolved config with no errors (this works even without a real `.env` filled in, since `docker compose config` doesn't require the referenced env values to be valid Supabase credentials — only that `srwiki-be/.env` exists; if it doesn't yet, create it from `.env.template` first per Task 12)

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: add root docker-compose for local dev"
```

---

## Phase C — Integration & Deploy

### Task 30: Deploy the frontend to Netlify

**Files:** none (CLI actions only)

**Prerequisites:** Task 28 (`netlify.toml`) done; `srwiki-fe` builds cleanly; the user has already run `netlify login` in their terminal (interactive OAuth — cannot be done non-interactively).

- [ ] **Step 1: Confirm the Netlify CLI is available**

```bash
netlify --version || npm install -g netlify-cli
```

- [ ] **Step 2: Confirm the user is authenticated**

```bash
netlify status
```

Expected: shows a logged-in account. If it shows "Not logged in", stop here and ask the user to run `netlify login` themselves — this step cannot be completed non-interactively.

- [ ] **Step 3: Link or create the site**

```bash
cd srwiki-fe
netlify init
```

Follow the prompts to either link to an existing site or create a new one.

- [ ] **Step 4: Deploy a draft build first**

```bash
netlify deploy --build
```

Expected: prints a draft URL. Open it and smoke-test `/auth/login` renders (the backend won't be reachable yet unless `VITE_API_BASE_URL` on Netlify points at a running backend — set that env var in the Netlify site's dashboard under Site configuration → Environment variables before the production deploy).

- [ ] **Step 5: After confirming the draft looks right, deploy to production**

```bash
netlify deploy --build --prod
```

Expected: prints the live production URL.

---

### Task 31: Manual end-to-end QA

**Files:** none (verification only)

**Prerequisites:** Task 12 (real Supabase project + migrations applied) done; backend and frontend both buildable.

- [ ] **Step 1: Start the backend**

```bash
cd srwiki-be
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 2: Start the frontend**

```bash
cd srwiki-fe
echo "VITE_API_BASE_URL=http://localhost:8000" > .env
npm run dev
```

- [ ] **Step 3: Drive the full flow in a browser using the Playwright MCP tools**

Navigate to `http://localhost:5173/auth/register`, fill in a test email/password/name, submit, confirm the success toast and redirect to `/auth/login`. Log in with the same credentials, confirm redirect to `/dashboard` and that the nav renders on the right with Dashboard/Hồ sơ/Đăng xuất. Go to `/profile`, fill in address and date of birth, save, confirm the success toast. Enter a phone number (with the country selector), click Xác thực, read the `debug_otp` value from the toast, enter it in the modal, confirm the "Đã xác thực" badge appears. Click Xoá tài khoản, confirm the browser dialog, confirm redirect to `/auth/login`. Attempt to log in again with the deleted account's credentials and confirm it fails.

- [ ] **Step 4: Report results**

Note any step that didn't behave as described — this is the final acceptance check for the whole plan, not a step to silently work around.

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. Use **superpowers:subagent-driven-development**.
2. **Inline Execution** — execute tasks in this session using **superpowers:executing-plans**, batch execution with checkpoints.

