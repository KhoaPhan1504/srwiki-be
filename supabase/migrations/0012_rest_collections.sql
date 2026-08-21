create table public.rest_collections (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);

create index rest_collections_user_id_idx on public.rest_collections (user_id);

create table public.rest_saved_requests (
  id uuid primary key default gen_random_uuid(),
  collection_id uuid not null references public.rest_collections (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  name text not null,
  method text not null,
  url text not null,
  query_params jsonb not null default '[]'::jsonb,
  headers jsonb not null default '[]'::jsonb,
  body text not null default '',
  body_type text not null default 'raw',
  body_fields jsonb not null default '[]'::jsonb,
  auth jsonb not null default '{"type":"none"}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index rest_saved_requests_collection_id_idx
  on public.rest_saved_requests (collection_id, created_at);

alter table public.rest_collections enable row level security;
alter table public.rest_saved_requests enable row level security;

create policy "Users can view their own rest collections"
  on public.rest_collections for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can create their own rest collections"
  on public.rest_collections for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "Users can update their own rest collections"
  on public.rest_collections for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete their own rest collections"
  on public.rest_collections for delete
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can view their own rest saved requests"
  on public.rest_saved_requests for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can create their own rest saved requests"
  on public.rest_saved_requests for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "Users can update their own rest saved requests"
  on public.rest_saved_requests for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete their own rest saved requests"
  on public.rest_saved_requests for delete
  to authenticated
  using (auth.uid() = user_id);
