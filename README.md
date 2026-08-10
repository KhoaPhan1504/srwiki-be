# SR-WIKI Backend

FastAPI backend for SR-WIKI's auth CRUD starter: register/login/refresh/logout, profile
read/update, phone number verification via OTP, and account deletion — backed by Supabase
(Auth + Postgres with Row Level Security).

Live deployment: https://srwiki-be.onrender.com (auto-deploys from `main`, free tier —
the service sleeps after ~15 min idle; the first request after that takes 30-60s).

## Requirements

- Python 3.12+
- A Supabase project (see [Supabase setup](#supabase-setup) below)

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.template .env
# then fill in .env — see below
```

`.env` variables:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Project URL, from Supabase → Project Settings → API |
| `SUPABASE_ANON_KEY` | `anon`/`publishable` key, same page |
| `SUPABASE_SERVICE_ROLE_KEY` | `service_role`/`secret` key, same page — never expose this client-side |
| `OTP_DEBUG_MODE` | `true` in dev: `POST /profile/phone/send-otp` echoes the generated code back in the response (no SMS provider is wired up yet) and logs it to the console. Set `false` once a real SMS provider is in place. |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins, e.g. `http://localhost:5173,https://srwiki-fe.netlify.app` |

## Supabase setup

1. Create a project at [supabase.com/dashboard](https://supabase.com/dashboard).
2. Project Settings → API → copy the URL, anon/publishable key, and service_role/secret
   key into `.env`.
3. Authentication → Sign In / Providers → Email → decide whether to keep "Confirm email"
   on. If it's on, Supabase sends a confirmation email on every signup, which is subject
   to its (very low, on the free tier) email rate limit — fine for occasional testing,
   easy to hit during rapid iteration. Turning it off skips the email step entirely.
4. SQL Editor → run the contents of `supabase/migrations/0001_profiles.sql`, then
   `supabase/migrations/0002_otp_codes.sql`. Confirm both tables show up under Table
   Editor with RLS enabled (shield icon).

## Running locally

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

API docs (Swagger UI) at `http://localhost:8000/docs` once running.

## Tests

```bash
source .venv/bin/activate
pytest -v
```

## Git hooks

```bash
source .venv/bin/activate
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

Runs automatically on `git commit`: Black + Ruff format/lint staged `.py` files
(blocking the commit on unresolved errors), and commitlint enforces
`type: short description` commit messages (Conventional Commits).

## Docker

```bash
docker build -t srwiki-be .
docker run -p 8000:8000 --env-file .env srwiki-be
```

Or from the SR-WIKI repo root, run both backend and frontend together via
`docker compose up` (see the root `docker-compose.yml`).

## Deployment

Deployed on [Render](https://render.com) (free tier) as a Docker web service, connected
to this repo's `main` branch — pushing to `main` triggers an automatic rebuild + deploy.
Environment variables are set in the Render dashboard under the service's Environment
tab (same keys as `.env.template`, plus `CORS_ORIGINS` should include the live frontend
URL). `Procfile` is also included for platforms that use buildpacks instead of the
Dockerfile (e.g. Railway).

## API overview

All JSON fields are camelCase (e.g. `fullName`, not `full_name`).

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | — | `{email, password, full_name}` |
| POST | `/auth/login` | — | returns `{token, refreshToken, user}` |
| POST | `/auth/refresh` | — | `{refreshToken}` |
| POST | `/auth/logout` | Bearer | |
| GET | `/profile` | Bearer | |
| PUT | `/profile` | Bearer | `{fullName?, address?, dateOfBirth?, bio?}` — never accepts `phone` |
| POST | `/profile/avatar` | Bearer | multipart `file` (png/jpeg/webp, ≤2MB) — uploads to Supabase Storage bucket `avatars`, updates `avatarUrl` |
| GET | `/settings` | Bearer | returns `{language, timezone, theme, emailNotifications}`, defaults if unset |
| PUT | `/settings` | Bearer | any subset of the 4 settings fields — partial-merges into stored settings |
| POST | `/profile/phone/send-otp` | Bearer | `{phone}` in E.164 format |
| POST | `/profile/phone/verify-otp` | Bearer | `{phone, code}` |
| DELETE | `/profile` | Bearer | deletes the account |
