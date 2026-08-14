-- Roles live in their own reference table (not a hardcoded CHECK constraint)
-- so adding a new role later is a plain INSERT, not a schema migration.
create table public.roles (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  created_at timestamptz not null default now()
);

alter table public.roles enable row level security;
-- No policies: only service_role (admin_client, bypasses RLS) reads/writes
-- roles today — same "RLS enabled, zero policies" pattern used for
-- known_logins (0007) for a table clients never query directly.

-- Fixed (not random) ids so 'member' can be referenced as a column DEFAULT
-- below — Postgres column defaults can't contain a subquery.
insert into public.roles (id, name) values
  ('00000000-0000-0000-0000-000000000001', 'admin'),
  ('00000000-0000-0000-0000-000000000002', 'member');

alter table public.profiles
  add column email text,
  add column role_id uuid not null default '00000000-0000-0000-0000-000000000002' references public.roles (id),
  add column membership_tier text default 'regular',
  add column deleted_at timestamptz;

alter table public.profiles
  add constraint profiles_membership_tier_check
    check (membership_tier in ('regular', 'vip') or membership_tier is null);

-- Existing rows already get role_id='member', membership_tier='regular' from
-- the column defaults above. Only email needs an explicit backfill
-- (denormalized from auth.users so admin listing/filtering never needs an
-- N+1 Admin API call per row — see spec section 4.0).
update public.profiles p
set email = u.email
from auth.users u
where p.id = u.id and p.email is null;

create index profiles_role_id_idx on public.profiles (role_id);
create index profiles_membership_tier_idx on public.profiles (membership_tier);
create index profiles_created_at_idx on public.profiles (created_at);
create index profiles_date_of_birth_idx on public.profiles (date_of_birth);
