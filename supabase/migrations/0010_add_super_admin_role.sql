-- Roles get simple, fixed small integer ids instead of opaque UUIDs, combined
-- here with adding the super_admin role since both require rebuilding
-- roles.id before more roles get added. Final ids: 1=super_admin, 2=admin,
-- 3=member, mirrored by the RoleId enum in app/permissions.py — so the
-- backend never has to look a role's id up by name again.

-- 1. Drop the FK on profiles so both id columns can change type.
alter table public.profiles drop constraint if exists profiles_role_id_fkey;

-- 2. Give roles a smallint id, populated from the existing UUID rows, then
--    add super_admin directly with its final id (it never had a UUID row).
alter table public.roles add column new_id smallint unique;
update public.roles set new_id = case name
  when 'admin' then 2
  when 'member' then 3
end;
insert into public.roles (id, name, new_id) values
  (gen_random_uuid(), 'super_admin', 1);

alter table public.roles drop constraint roles_pkey;
alter table public.roles drop column id;
alter table public.roles rename column new_id to id;
alter table public.roles alter column id set not null;
alter table public.roles add primary key (id);

-- 3. Mirror the same id swap on profiles.role_id, mapping each profile's
--    current (uuid) role assignment to the matching new smallint id.
alter table public.profiles add column new_role_id smallint;
update public.profiles p
set new_role_id = case
  when p.role_id = '00000000-0000-0000-0000-000000000001' then 2  -- admin
  when p.role_id = '00000000-0000-0000-0000-000000000002' then 3  -- member
end;
alter table public.profiles drop column role_id;
alter table public.profiles rename column new_role_id to role_id;
alter table public.profiles alter column role_id set not null;
alter table public.profiles alter column role_id set default 3;
alter table public.profiles add constraint profiles_role_id_fkey
  foreign key (role_id) references public.roles (id);

create index profiles_role_id_idx on public.profiles (role_id);
