create table public.user_settings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users (id) on delete cascade,
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index user_settings_user_id_idx on public.user_settings (user_id);

alter table public.user_settings enable row level security;

create policy "Users can view their own settings"
  on public.user_settings for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can update their own settings"
  on public.user_settings for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can insert their own settings"
  on public.user_settings for insert
  to authenticated
  with check (auth.uid() = user_id);
