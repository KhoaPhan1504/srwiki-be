create table public.known_logins (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  device_hash text not null,
  ip_address text,
  user_agent text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique (user_id, device_hash)
);

create index known_logins_user_id_idx on public.known_logins (user_id);

alter table public.known_logins enable row level security;
