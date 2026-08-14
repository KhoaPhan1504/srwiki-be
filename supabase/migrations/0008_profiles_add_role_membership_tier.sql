alter table public.profiles
  add column email text,
  add column role text not null default 'member',
  add column membership_tier text default 'regular',
  add column deleted_at timestamptz;

alter table public.profiles
  add constraint profiles_role_check check (role in ('admin', 'member')),
  add constraint profiles_membership_tier_check
    check (membership_tier in ('regular', 'vip') or membership_tier is null);

-- Existing rows already get role='member', membership_tier='regular' from the
-- column defaults above. Only email needs an explicit backfill (denormalized
-- from auth.users so admin listing/filtering never needs an N+1 Admin API call
-- per row — see spec section 4.0).
update public.profiles p
set email = u.email
from auth.users u
where p.id = u.id and p.email is null;

create index profiles_role_idx on public.profiles (role);
create index profiles_membership_tier_idx on public.profiles (membership_tier);
create index profiles_created_at_idx on public.profiles (created_at);
create index profiles_date_of_birth_idx on public.profiles (date_of_birth);
