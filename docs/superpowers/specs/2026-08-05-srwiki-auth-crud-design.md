# SR-WIKI Auth CRUD Starter — Design Spec

Date: 2026-08-05
Status: Approved by user, pending spec review

## Goal

Bootstrap the SR-WIKI project: a Python backend (FastAPI) backed by Supabase (Auth +
Postgres), and a React frontend (Vite + TS) deployed to Netlify. Users can register,
log in, and land on a Dashboard with a right-side nav. From a Profile page they can
view/edit their info (full name, address, date of birth), verify a phone number via
OTP, and delete their account — i.e. full CRUD on the user's own profile.

This is an initial scaffold ("khởi tạo dự án"): the goal is a correctly wired,
working skeleton with the patterns below in place, not a feature-complete product.

## Non-goals

- Real SMS delivery for OTP (dev-mode only; see "OTP flow" below).
- Production deployment of the backend (Render/Railway config is prepared, but
  account creation and the actual deploy are left to the user).
- Any authorization/roles system. The 403 "access-removed" handling is scaffolded
  per the user's existing company frontend convention but nothing in this project
  currently triggers it.
- Frontend automated test suite (see "Testing scope").

## Architecture

```
┌─────────────┐      HTTPS/JSON       ┌──────────────┐      supabase-py      ┌───────────┐
│  React FE   │ ───────────────────▶ │  FastAPI BE   │ ────────────────────▶ │ Supabase  │
│ srwiki-fe   │ ◀─────────────────── │  srwiki-be    │ ◀──────────────────── │ Auth + DB │
│ (Netlify)   │   Bearer JWT token    │ (local→Render)│                       └───────────┘
└─────────────┘                       └──────────────┘
```

The frontend never talks to Supabase directly. All Auth and data operations go
through the FastAPI backend. The Supabase service-role key exists only on the
backend and is never sent to the client.

## Auth flow

1. **Register** — `POST /auth/register {email, password, full_name}`. Backend calls
   Supabase Auth `sign_up` (anon key), then inserts a row into `profiles`. Depending
   on the Supabase project's email-confirmation setting, the user may need to
   confirm their email before logging in (documented in the setup guide; can be
   disabled for local dev).
2. **Login** — `POST /auth/login {email, password}`. Backend calls
   `sign_in_with_password`, returns `{token, refreshToken, user}`. On success the FE
   stores this and **navigates to `/dashboard`**.
3. **Refresh** — `POST /auth/refresh {refreshToken}`. Backend calls Supabase
   `auth.refresh_session(refresh_token)` and returns a new `{token, refreshToken,
   user}` (rotated refresh token). Used by the FE axios interceptor to silently
   recover from an expired access token (see "Frontend HTTP client").
4. **Authenticated requests** — FE sends `Authorization: Bearer <token>`. A FastAPI
   dependency (`get_current_user`) validates the token against Supabase and yields
   the user.
5. **Profile reads/writes** — the backend makes the Supabase Postgres call using the
   *user's own access token* (not the service-role key), so Row Level Security (RLS)
   is enforced normally. Service-role is reserved for operations only an admin API
   can do (deleting a user).
6. **Logout** — FE calls `POST /auth/logout` (Bearer-authenticated, fire-and-forget)
   then clears `auth` and `refreshToken` from localStorage and the `authAtom`. The
   endpoint only validates the caller's token and returns `204`; it does not call
   out to Supabase to explicitly revoke the session, since the Python SDK doesn't
   cleanly support revoking an arbitrary token outside its own client session
   state. Session invalidation is left to the access token's natural expiry — safe
   for a short-lived JWT, and consistent with clearing local state client-side
   regardless of whether the network call succeeds.

Response bodies are flat JSON matching the resource directly — no `{data: ...}`
envelope — to match the existing company frontend convention where interceptors
read fields like `data.token` straight off the axios response body.

## Backend design (`srwiki-be/`)

### Structure

```
srwiki-be/
  app/
    main.py                # FastAPI app, CORS, router registration
    config.py               # pydantic Settings, reads .env
    supabase_client.py      # admin_client(), anon_client(), user_client(token)
    dependencies.py         # get_current_user
    schemas.py               # Pydantic request/response models
    phone.py                  # phone parsing/validation helpers (phonenumbers)
    routers/
      auth.py                 # /auth/register, /auth/login, /auth/refresh, /auth/logout
      profile.py               # /profile (GET/PUT/DELETE), /profile/phone/*
  tests/
    test_auth.py
    test_profile.py
  supabase/
    migrations/
      0001_profiles.sql       # profiles table + RLS policies
      0002_otp_codes.sql      # otp_codes table (service-role only)
  requirements.txt
  Dockerfile
  Procfile                    # for Render/Railway
  .env.template
  .gitignore
```

### Supabase clients

Three ways the backend talks to Supabase, used for different purposes:

- **`anon_client()`** — anon key. Used for `sign_up`, `sign_in_with_password`,
  `refresh_session` — the public, unauthenticated Auth operations.
- **`user_client(access_token)`** — anon key client with the request's access token
  attached to PostgREST (`client.postgrest.auth(access_token)`). Used for all
  `profiles` reads/writes so RLS applies normally (`auth.uid() = id`).
- **`admin_client()`** — service-role key, used only for `auth.admin.delete_user`
  (account deletion) and token verification in `get_current_user`. Never exposed to
  the client.

### Database schema

**`profiles`**

| column | type | notes |
|---|---|---|
| id | uuid PK | = `auth.users.id`, FK `on delete cascade` |
| full_name | text | |
| phone | text, nullable | set only via the OTP verify flow, never via `PUT /profile` |
| phone_verified | boolean, default false | reset to false whenever `phone` changes |
| address | text, nullable | editable via `PUT /profile` |
| date_of_birth | date, nullable | editable via `PUT /profile` |
| created_at | timestamptz, default now() | |
| updated_at | timestamptz, default now() | |

RLS enabled: policy `auth.uid() = id` for select/update on own row.

**`otp_codes`** (internal bookkeeping — RLS enabled with no policies, so only the
service-role client can touch it; anon/authenticated roles get nothing)

| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → auth.users, on delete cascade | |
| phone | text | E.164 format |
| code | text | 6 digits |
| expires_at | timestamptz | `created_at + 5 minutes` |
| consumed | boolean, default false | |
| created_at | timestamptz, default now() | |

### API endpoints

| Method | Path | Auth | Body | Notes |
|---|---|---|---|---|
| POST | `/auth/register` | none | `{email, password, full_name}` | creates auth user + profile row |
| POST | `/auth/login` | none | `{email, password}` | returns `{token, refreshToken, user}` |
| POST | `/auth/refresh` | none | `{refreshToken}` | returns rotated `{token, refreshToken, user}` |
| POST | `/auth/logout` | Bearer | — | best-effort session revoke |
| GET | `/profile` | Bearer | — | returns current user's profile |
| PUT | `/profile` | Bearer | `{full_name?, address?, date_of_birth?}` | never accepts `phone` |
| POST | `/profile/phone/send-otp` | Bearer | `{phone}` (E.164) | validates via `phonenumbers`, generates + stores OTP |
| POST | `/profile/phone/verify-otp` | Bearer | `{phone, code}` | on success sets `phone` + `phone_verified=true` |
| DELETE | `/profile` | Bearer | — | admin-deletes the auth user; cascades `profiles`/`otp_codes` |

### Phone validation

The FE collects a country + national number via `react-phone-number-input` and
sends the value already formatted as E.164 (e.g. `+84912345678`). The backend
re-validates independently using the `phonenumbers` library (Python port of
Google's libphonenumber, the same engine `react-phone-number-input` uses under the
hood via `libphonenumber-js`) — parses the E.164 string and rejects with `422` if
it's not a valid, possible number for its region. The backend never trusts
client-side validation alone.

### OTP flow (dev mode)

1. `POST /profile/phone/send-otp {phone}` — generate a random 6-digit code,
   invalidate the user's prior unconsumed codes, insert a row into `otp_codes` with
   `expires_at = now() + 5 minutes`. Always log the code to the console. When
   `OTP_DEBUG_MODE=true` (the default in `.env.template`), also return it in the
   response as `debug_otp` so the flow is testable without a real SMS provider.
   Setting `OTP_DEBUG_MODE=false` removes the field — that's the seam for plugging
   in a real SMS provider later (Twilio/Vonage/etc. — out of scope for this pass).
2. `POST /profile/phone/verify-otp {phone, code}` — look up the newest unconsumed,
   unexpired code for the current user + phone. Match → mark consumed, update
   `profiles.phone`/`phone_verified`. No match or expired → `400`.
3. If the user later changes their phone number, `phone_verified` resets to `false`
   until they re-verify.

### Testing scope

Backend gets `pytest` tests for the auth and profile routers with the Supabase
client mocked/dependency-overridden — covering register/login happy paths, invalid
phone rejection, OTP expiry/mismatch, and the delete-cascade contract. Frontend
testing is out of scope for this pass (lint + type-check is the quality gate);
Vitest/RTL can be added later if needed.

## Frontend design (`srwiki-fe/`)

Vite + React + TypeScript + Tailwind CSS, following the user's existing company
frontend conventions rather than a from-scratch structure.

### Structure

```
srwiki-fe/
  src/
    apis/                 # useLogin, useRegister, useGetProfile, useUpdateProfile,
                           # useSendOtp, useVerifyOtp, useDeleteAccount, useRefreshToken
    constants/             # index.ts — API_URL, Endpoints
    lib/                   # http-client.ts
    stores/                 # jotai store instance (localStore)
    screens/
      auth/login/            # LoginPage.tsx, stores.ts (authAtom)
      auth/register/
      auth/access-removed/    # scaffolded per company convention, unused for now
      dashboard/
      profile/
    components/              # Sidebar, ProtectedRoute, OtpModal, PhoneInput
    utils/                    # isJsonString, ...
  netlify.toml
  Dockerfile
  .env.template
  .gitignore
  .eslintrc / eslint.config.*
  .prettierrc
```

### Path alias

`~root/*` → `src/*`, configured in both `vite.config.ts` (resolve.alias) and
`tsconfig.json` (paths), matching the import style already used in the reference
code (`~root/constants`, `~root/lib/http-client`, `~root/screens/...`).

### HTTP client

`src/lib/http-client.ts` reuses the exact pattern the user provided: axios instance
with `baseURL: API_URL`, request interceptor attaching `Authorization: Bearer` from
`localStorage['auth']`, and a response interceptor that:

- On `401` (outside the login page): queues concurrent requests, calls
  `Endpoints.AUTH_REFRESH` with the stored `refreshToken`, retries queued requests
  with the new token, and redirects to `/auth/login?callbackUrl=...` (with a toast)
  if refresh itself fails.
- On `403` with `errorCode: NOT_AUTHORIZED_TO_USE_APPLICATION`: redirects to
  `/auth/access-removed`. This case is unreachable today since no backend endpoint
  emits that error code — it's scaffolding for a future permissions feature, kept
  because the user asked to preserve it.
- Otherwise on `403`: generic toast.

### State & data fetching

- **Jotai** for auth state: `authAtom` holds `{token, user}`, kept in sync with
  `localStorage['auth']`; `refreshToken` is stored under its own localStorage key,
  matching the reference code.
- **`@tanstack/react-query`** for every API call, following the
  `useGetDataSource`-style pattern: an internal async fetch function + `useQuery`
  (reads) or `useMutation` (writes), one hook per operation in `src/apis/`.

### Routing

React Router v6:

- `/auth/login`, `/auth/register`, `/auth/access-removed` — public
- `/dashboard`, `/profile` — behind `ProtectedRoute` (redirects to
  `/auth/login?callbackUrl=...` if no valid session)

### Dashboard

Layout with a fixed nav on the **right** side of the screen (links: Dashboard,
Profile, Đăng xuất). Main content area is placeholder cards — content is
intentionally arbitrary per the request; only the right-side nav placement is a
hard requirement.

### Profile page

Form for `full_name` / `address` / `date_of_birth` (Save button, via
`useUpdateProfile`). Separate phone field with a "Xác thực" button that opens
`OtpModal`:

- Phone input uses `react-phone-number-input` (country dropdown with flags,
  default country Vietnam `+84`, produces an E.164-formatted value).
- `OtpModal`: 6-digit code entry, 5-minute countdown, resend button (re-calls
  `send-otp`).
- "Xoá tài khoản" button at the bottom, behind a confirm dialog, calls
  `useDeleteAccount` → on success clears auth state and redirects to `/auth/login`.

### Lint/format

ESLint (typescript-eslint + react-hooks + react-refresh, Vite's standard template
baseline) + Prettier, with `eslint-config-prettier` to disable stylistic rules that
would conflict with Prettier.

## Docker & environment files

Both `srwiki-be/` and `srwiki-fe/` get:

- `Dockerfile`
  - Backend: `python:3.12-slim`, installs `requirements.txt`, runs
    `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (defaults to 8000 locally;
    Render/Railway inject `$PORT`).
  - Frontend: multi-stage — `node:20-alpine` build stage (`npm ci && npm run
    build`), then `nginx:alpine` serving stage copying `dist/` to
    `/usr/share/nginx/html`. This is for local/dev containerized preview; Netlify
    remains the actual deployment target.
- `.env.template` — committed to git, lists every variable needed with empty/example
  values (no real secrets).
- `.env` — gitignored. Created locally by the user by copying `.env.template` and
  filling in real values (Supabase URL/keys for BE, API base URL for FE).

A `docker-compose.yml` at the repo root runs both services together for local dev
(`docker compose up`): backend on port 8000, frontend nginx container fronting the
built static files.

## Deployment

- **Frontend → Netlify**: `netlify.toml` with `npm run build`, publish `dist`, and
  an SPA redirect rule (`/* → /index.html 200`) so client-side routing works on
  refresh. The build will be deployed via `netlify deploy` — this requires the user
  to run `netlify login` first (interactive OAuth Claude cannot perform).
- **Backend → Render/Railway**: `Procfile` and `Dockerfile` are prepared so either
  platform can build and run the service, but creating the account/project and
  connecting it is left to the user for this pass (see Non-goals).

## Supabase project setup (user action required)

The user does not yet have a Supabase project. Since the Supabase MCP integration
isn't authenticated in this environment, this can't be created programmatically —
the spec's implementation plan will include a step-by-step guide (create project at
supabase.com, copy the URL + anon key + service-role key into `srwiki-be/.env`,
optionally disable email-confirmation for faster local testing, and run the SQL
migrations in `supabase/migrations/` via the SQL editor or Supabase CLI) rather than
an automated step.
