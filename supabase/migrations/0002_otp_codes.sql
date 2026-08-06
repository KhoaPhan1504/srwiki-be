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
