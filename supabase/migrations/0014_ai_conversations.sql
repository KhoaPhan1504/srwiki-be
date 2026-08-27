create table public.ai_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index ai_conversations_user_id_updated_at_idx
  on public.ai_conversations (user_id, updated_at desc);

create table public.ai_conversation_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.ai_conversations (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  seq bigint generated always as identity,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create unique index ai_conversation_messages_conversation_seq_idx
  on public.ai_conversation_messages (conversation_id, seq);

alter table public.ai_conversations enable row level security;
alter table public.ai_conversation_messages enable row level security;

create policy "Users can view their own ai conversations"
  on public.ai_conversations for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can create their own ai conversations"
  on public.ai_conversations for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "Users can update their own ai conversations"
  on public.ai_conversations for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users can delete their own ai conversations"
  on public.ai_conversations for delete
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can view their own ai conversation messages"
  on public.ai_conversation_messages for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Users can create their own ai conversation messages"
  on public.ai_conversation_messages for insert
  to authenticated
  with check (auth.uid() = user_id);
