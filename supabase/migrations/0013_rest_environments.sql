create table public.rest_environments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  variables jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index rest_environments_user_id_idx on public.rest_environments (user_id);

alter table public.rest_environments enable row level security;

create policy "Users can view their own rest environments"
  on public.rest_environments for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can create their own rest environments"
  on public.rest_environments for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "Users can update their own rest environments"
  on public.rest_environments for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete their own rest environments"
  on public.rest_environments for delete
  to authenticated
  using (auth.uid() = user_id);

create table public.rest_global_variables (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users (id) on delete cascade,
  variables jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index rest_global_variables_user_id_idx on public.rest_global_variables (user_id);

alter table public.rest_global_variables enable row level security;

create policy "Users can view their own rest global variables"
  on public.rest_global_variables for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can update their own rest global variables"
  on public.rest_global_variables for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can insert their own rest global variables"
  on public.rest_global_variables for insert
  to authenticated
  with check (auth.uid() = user_id);
